import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { shortModelName } from "../../utils/models";
import { nextId, nextRequestId } from "../../shared/lib/id";
import { useSessionRepository } from "../sessions/sessionRepositoryContext";
import { SESSION_LIST_QUERY_KEY, sessionDetailQueryKey } from "../sessions/useSessions";
import { NEW_SESSION_KEY, useChatUiStore, hasGlobalPending } from "../../shared/store/chatUiStore";
import { buildSessionTitle } from "../../entities/session/sessionSummary";
import { toApiHistory } from "./history";
import { useStreamController } from "./useStreamController";
import { mapStreamEventToPatch } from "./mapStreamEventToPatch";

async function syncSessionToCache(queryClient, repository, sessionId) {
  const session = await repository.getSession(sessionId);
  queryClient.setQueryData(sessionDetailQueryKey(sessionId), session);
  await queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
  return session;
}

function patchStreamMessageInCache(queryClient, sessionId, streamId, event) {
  const prev = queryClient.getQueryData(sessionDetailQueryKey(sessionId));
  if (!prev) return;
  queryClient.setQueryData(sessionDetailQueryKey(sessionId), {
    ...prev,
    messages: prev.messages.map((msg) =>
      msg.id === streamId ? mapStreamEventToPatch(msg, event) : msg
    ),
  });
}

export function useSendMessage({
  model,
  webSearch,
  thinkingMode,
  supportsThinking,
  supportsMedia,
  attachments,
  clearAttachments,
}) {
  const repository = useSessionRepository();
  const queryClient = useQueryClient();
  const { startStream, abortStream } = useStreamController();
  const sendingRef = useRef(false);

  const onSubmit = useCallback(
    async (event) => {
      event.preventDefault();

      // Synchronous mutex, prevents race between state reads and startRequest.
      if (sendingRef.current) return;
      sendingRef.current = true;

      try {
        const state = useChatUiStore.getState();
        const currentSessionId = state.activeSessionId;
        const input = state.getDraft(currentSessionId);
        const text = input.trim();

        if (!text) {
          return;
        }
        if (hasGlobalPending(state.pendingBySessionId)) {
          return;
        }

        const effectiveThinking = supportsThinking ? thinkingMode : true;
        const mediaUrls = supportsMedia ? attachments.map((item) => item.dataUrl) : [];

        let sessionId = currentSessionId;
        let session = null;

        if (sessionId) {
          session = await repository.getSession(sessionId);
        }

        if (!session) {
          sessionId = nextId("session");
          session = await repository.createSession({
            id: sessionId,
            title: buildSessionTitle(text),
            settings: {
              model,
              webSearch,
              thinkingMode: effectiveThinking,
            },
          });
          useChatUiStore.getState().setActiveSessionId(sessionId);
        }

        // Single global in-flight stream policy.
        if (hasGlobalPending(useChatUiStore.getState().pendingBySessionId)) {
          return;
        }

        const requestId = nextRequestId();
        const userId = nextId("msg");
        const streamId = nextId("msg");
        const tags = [shortModelName(model)];
        if (webSearch) tags.push("Search");
        if (supportsThinking) tags.push(effectiveThinking ? "Thinking" : "Instant");
        if (mediaUrls.length > 0) tags.push(`Media x${mediaUrls.length}`);

        const userMessage = { id: userId, role: "user", content: `[${tags.join("] [")}]\n${text}` };
        const streamMessage = {
          id: streamId,
          requestId,
          role: "assistant_stream",
          status: "streaming",
          search: { state: "hidden", query: "", results: [], error: "" },
          usageLines: [],
          reasoning: "",
          answer: "Thinking...",
        };

        await repository.appendMessages(sessionId, [userMessage, streamMessage]);
        await syncSessionToCache(queryClient, repository, sessionId);

        useChatUiStore.getState().setDraft(sessionId, "");
        clearAttachments();
        useChatUiStore.getState().startRequest(sessionId, requestId);

        const history = toApiHistory(session.messages);
        let finalized = false;
        let terminalErrorText = "";

        const finalizeStreamOnce = async (cause, payload = {}) => {
          if (finalized) return;
          finalized = true;

          if (!useChatUiStore.getState().isCurrentRequest(sessionId, requestId)) {
            // Request is stale (e.g. store reset during HMR/unmount).
            // Still finalize the message in the repository to avoid stuck "streaming" status.
            try {
              await repository.updateMessage(sessionId, streamId, (msg) => {
                if (msg.status !== "streaming") return msg;
                return { ...msg, status: "done", answer: msg.answer || "(stale)" };
              });
            } catch { /* best-effort */ }
            return;
          }

          try {
            const errorText = payload.errorText || terminalErrorText;
            if (cause === "error" || (cause === "done" && errorText)) {
              const finalErrorText = errorText || "Request failed";
              await repository.updateMessage(sessionId, streamId, (message) => {
                if (message.status !== "streaming") return message;
                return {
                  ...message,
                  status: "failed",
                  answer: `Error: ${finalErrorText}`,
                };
              });
              await syncSessionToCache(queryClient, repository, sessionId);
              useChatUiStore.getState().failRequest(sessionId, finalErrorText);
              return;
            }

            if (cause === "aborted") {
              await repository.updateMessage(sessionId, streamId, (msg) => {
                if (msg.status !== "streaming") return msg;
                const answer =
                  msg.answer && msg.answer !== "Thinking..."
                    ? msg.answer
                    : "Canceled by user.";
                return { ...msg, status: "done", answer };
              });
              await syncSessionToCache(queryClient, repository, sessionId);
              useChatUiStore.getState().finishRequest(sessionId);
              return;
            }

            await repository.updateMessage(sessionId, streamId, (msg) => {
              if (msg.status !== "streaming") return msg;
              const answer = !msg.answer || msg.answer === "Thinking..." ? "(empty response)" : msg.answer;
              return { ...msg, status: "done", answer };
            });
            await syncSessionToCache(queryClient, repository, sessionId);
            useChatUiStore.getState().finishRequest(sessionId);
          } catch {
            // Guarantee pending lock release even if repository/cache operations fail.
            useChatUiStore.getState().finishRequest(sessionId);
          }
        };

        await startStream({
          payload: {
            request_id: requestId,
            message: text,
            history,
            model,
            web_search: webSearch,
            thinking_mode: effectiveThinking,
            images: mediaUrls,
          },
          onEvent: async (streamEvent) => {
            const active = useChatUiStore.getState().isCurrentRequest(sessionId, requestId);
            if (!active) {
              return;
            }

            if (streamEvent.type === "error") {
              terminalErrorText = streamEvent.error || "Streaming request failed";
              return;
            }
            if (streamEvent.type === "done") {
              return;
            }

            await repository.updateMessage(sessionId, streamId, (message) => mapStreamEventToPatch(message, streamEvent));
            patchStreamMessageInCache(queryClient, sessionId, streamId, streamEvent);
          },
          onDone: async () => {
            await finalizeStreamOnce("done");
          },
          onTransportError: async (errorText) => {
            await finalizeStreamOnce("error", { errorText });
          },
          onAborted: async () => {
            await finalizeStreamOnce("aborted");
          },
        });
      } finally {
        sendingRef.current = false;
      }
    },
    [
      attachments,
      clearAttachments,
      model,
      queryClient,
      repository,
      startStream,
      supportsMedia,
      supportsThinking,
      thinkingMode,
      webSearch,
    ],
  );

  // Abort any running stream on unmount to prevent orphaned pending state.
  useEffect(() => () => abortStream(), [abortStream]);

  const stopActiveSession = useCallback(() => {
    const state = useChatUiStore.getState();
    const activeSessionId = state.activeSessionId;
    if (!activeSessionId || activeSessionId === NEW_SESSION_KEY) return;
    if (!state.pendingBySessionId[activeSessionId]) return;
    abortStream();
  }, [abortStream]);

  return { onSubmit, stopActiveSession };
}
