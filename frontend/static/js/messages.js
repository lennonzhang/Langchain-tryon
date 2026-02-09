export function createMessageView(messagesEl) {
  function addMessage(role, content) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.textContent = content;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function updateMessage(el, content) {
    el.textContent = content;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  return {
    addMessage,
    updateMessage,
  };
}
