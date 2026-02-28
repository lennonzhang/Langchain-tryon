import { useEffect, useRef, useState } from "react";
import { parseEventStream } from "../stream";
import { CONNECTED_TEXT, shortModelName } from "../utils/models";

export function useChatStream({
  model,
  webSearch,
  thinkingMode,
  supportsThinking,
  supportsMedia,
  attachments,
  clearAttachments,
}) {
  const messagesRef = useRef(null);
  const idRef = useRef(2);
  const [messages, setMessages] = useState([{ id: 1, role: "assistant", content: CONNECTED_TEXT }]);
  const [history, setHistory] = useState([]);
  const [input, setInput] = useState("");
  const [isPending, setPending] = useState(false);

  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;

    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
    if (!isNearBottom) return;

    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [messages]);

  function nextId() {
    const id = idRef.current;
    idRef.current += 1;
    return id;
  }

  function updateStreamMessage(streamId, updater) {
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== streamId || msg.role !== "assistant_stream") return msg;
        return updater(msg);
      }),
    );
  }

  async function onSubmit(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || isPending) return;

    const effectiveThinking = supportsThinking ? thinkingMode : true;
    const mediaUrls = supportsMedia ? attachments.map((a) => a.dataUrl) : [];
    const tags = [shortModelName(model)];
    if (webSearch) tags.push("Search");
    if (supportsThinking) tags.push(effectiveThinking ? "Thinking" : "Instant");
    if (mediaUrls.length > 0) tags.push(`Media x${mediaUrls.length}`);

    const userId = nextId();
    const streamId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: `[${tags.join("] [")}]\n${text}` },
      {
        id: streamId,
        role: "assistant_stream",
        search: { state: "hidden", query: "", results: [], error: "" },
        usageLines: [],
        reasoning: "",
        answer: "Thinking...",
      },
    ]);

    setInput("");
    clearAttachments();
    setPending(true);

    let answer = "";
    let streamFailed = false;
    try {
      const resp = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history,
          model,
          web_search: webSearch,
          thinking_mode: effectiveThinking,
          images: mediaUrls,
        }),
      });

      if (!resp.ok) {
        let detail = "Request failed";
        try {
          const err = await resp.json();
          detail = err.error || detail;
        } catch {}
        throw new Error(detail);
      }
      if (!resp.body) throw new Error("Browser does not support streaming");

      await parseEventStream(resp.body.getReader(), (evt) => {
        if (evt.type === "search_start") {
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            search: { state: "loading", query: evt.query || "", results: [], error: "" },
          }));
          return;
        }
        if (evt.type === "search_done") {
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            search: {
              state: "done",
              query: msg.search.query,
              results: Array.isArray(evt.results) ? evt.results : [],
              error: "",
            },
          }));
          return;
        }
        if (evt.type === "search_error") {
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            search: { state: "error", query: msg.search.query, results: [], error: evt.error || "" },
          }));
          return;
        }
        if (evt.type === "context_usage") {
          const usage = evt.usage || {};
          const phase = usage.phase || "unknown";
          const used = Number(usage.used_estimated_tokens || 0);
          const total = Number(usage.window_total_tokens || 0);
          const ratio = Number(usage.usage_ratio || 0);
          const pct = (ratio * 100).toFixed(2);
          const mn = usage.model ? ` - ${usage.model}` : "";
          const line = `[${phase}] ${used}/${total} tokens (${pct}%)${mn}`;
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            usageLines: [...msg.usageLines, line],
          }));
          return;
        }
        if (evt.type === "reasoning") {
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            reasoning: `${msg.reasoning}${evt.content || ""}`,
          }));
          return;
        }
        if (evt.type === "token") {
          answer += evt.content || "";
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            answer: answer || "Thinking...",
          }));
          return;
        }
        if (evt.type === "error") {
          streamFailed = true;
          throw new Error(evt.error || "Streaming request failed");
        }
      });

      if (streamFailed) {
        return;
      }

      if (!answer) {
        answer = "(empty response)";
        updateStreamMessage(streamId, (msg) => ({ ...msg, answer }));
      }

      setHistory((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: answer }]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Request failed";
      updateStreamMessage(streamId, (msg) => ({ ...msg, answer: `Error: ${message}` }));
    } finally {
      setPending(false);
    }
  }

  return { messages, input, setInput, isPending, onSubmit, messagesRef };
}
