function formatUsageLine(usage) {
  const phase = usage.phase || "unknown";
  const used = Number(usage.used_estimated_tokens || 0);
  const total = Number(usage.window_total_tokens || 0);
  const ratio = Number(usage.usage_ratio || 0);
  const pct = (ratio * 100).toFixed(2);
  const model = usage.model ? ` - ${usage.model}` : "";
  return `[${phase}] ${used}/${total} tokens (${pct}%)${model}`;
}

export function mapStreamEventToPatch(message, event) {
  if (!message || message.role !== "assistant_stream") {
    return message;
  }

  if (event.type === "search_start") {
    return {
      ...message,
      search: { state: "loading", query: event.query || "", results: [], error: "" },
    };
  }

  if (event.type === "search_done") {
    return {
      ...message,
      search: {
        state: "done",
        query: message.search.query,
        results: Array.isArray(event.results) ? event.results : [],
        error: "",
      },
    };
  }

  if (event.type === "search_error") {
    return {
      ...message,
      search: {
        state: "error",
        query: message.search.query,
        results: [],
        error: event.error || "",
      },
    };
  }

  if (event.type === "context_usage") {
    const usage = event.usage || {};
    return {
      ...message,
      usageLines: [...message.usageLines, formatUsageLine(usage)],
    };
  }

  if (event.type === "reasoning") {
    return {
      ...message,
      reasoning: `${message.reasoning}${event.content || ""}`,
    };
  }

  if (event.type === "token") {
    const answer = `${message.answer === "Thinking..." ? "" : message.answer}${event.content || ""}`;
    return {
      ...message,
      answer: answer || "Thinking...",
    };
  }

  if (event.type === "error") {
    return {
      ...message,
      status: "failed",
      answer: `Error: ${event.error || "Streaming request failed"}`,
    };
  }

  if (event.type === "done") {
    if (message.status === "failed") {
      return {
        ...message,
        status: "failed",
      };
    }

    const normalizedAnswer = !message.answer || message.answer === "Thinking..." ? "(empty response)" : message.answer;

    return {
      ...message,
      status: "done",
      answer: normalizedAnswer,
    };
  }

  return message;
}
