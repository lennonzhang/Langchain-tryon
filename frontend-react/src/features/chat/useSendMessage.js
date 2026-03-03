import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { shortModelName } from "../../utils/models";
import { nextId, nextRequestId } from "../../shared/lib/id";
import { useSessionRepository } from "../sessions/sessionRepositoryContext";
import { SESSION_LIST_QUERY_KEY, sessionDetailQueryKey } from "../sessions/useSessions";
import { useChatUiStore } from "../../shared/store/chatUiStore";
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
  const { startStream } = useStreamController();

  return useCallback(
    async (event) => {
      event.preventDefault();

      const state = useChatUiStore.getState();
      const currentSessionId = state.activeSessionId;
      const input = state.getDraft(currentSessionId);
      const text = input.trim();

      if (!text) {
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

      const pendingBySession = useChatUiStore.getState().pendingBySessionId;
      if (pendingBySession[sessionId]) {
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

          await repository.updateMessage(sessionId, streamId, (message) => mapStreamEventToPatch(message, streamEvent));

          if (streamEvent.type === "done") {
            const updated = await syncSessionToCache(queryClient, repository, sessionId);
            const streamEntry = updated?.messages?.find((msg) => msg.id === streamId);
            const failed = streamEntry?.status === "failed";
            if (failed) {
              useChatUiStore.getState().failRequest(sessionId, streamEntry.answer || "Request failed");
            } else {
              useChatUiStore.getState().finishRequest(sessionId);
            }
          } else {
            patchStreamMessageInCache(queryClient, sessionId, streamId, streamEvent);
          }
        },
        onDone: async () => {
          if (!useChatUiStore.getState().isCurrentRequest(sessionId, requestId)) {
            return;
          }
          await repository.updateMessage(sessionId, streamId, (msg) => {
            if (msg.status !== "streaming") return msg;
            const answer = !msg.answer || msg.answer === "Thinking..." ? "(empty response)" : msg.answer;
            return { ...msg, status: "done", answer };
          });
          await syncSessionToCache(queryClient, repository, sessionId);
          useChatUiStore.getState().finishRequest(sessionId);
        },
        onTransportError: async (errorText) => {
          if (!useChatUiStore.getState().isCurrentRequest(sessionId, requestId)) {
            return;
          }
          await repository.updateMessage(sessionId, streamId, (message) => ({
            ...message,
            status: "failed",
            answer: `Error: ${errorText}`,
          }));
          await syncSessionToCache(queryClient, repository, sessionId);
          useChatUiStore.getState().failRequest(sessionId, errorText);
        },
      });
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
}
