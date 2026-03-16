export function toApiHistory(messages) {
  const history = [];
  for (const message of messages || []) {
    if (message.role === "user") {
      history.push({ role: "user", content: message.content || "" });
      continue;
    }
    if (message.role === "assistant") {
      history.push({ role: "assistant", content: message.content || "" });
      continue;
    }
    if (message.role === "assistant_stream" && message.status === "done") {
      const content = message.clarification?.question || message.answer || "";
      history.push({ role: "assistant", content });
    }
  }
  return history;
}
