export function createChatState() {
  const history = [];

  function appendTurn(userMessage, assistantMessage) {
    history.push({ role: "user", content: userMessage });
    history.push({ role: "assistant", content: assistantMessage });
  }

  function snapshot() {
    return [...history];
  }

  return {
    appendTurn,
    snapshot,
  };
}
