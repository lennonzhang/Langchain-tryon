export function createDOMRefs() {
  const messagesEl = document.getElementById("messages");
  const formEl = document.getElementById("form");
  const inputEl = document.getElementById("input");
  const sendBtnEl = document.getElementById("sendBtn");

  return {
    messagesEl,
    formEl,
    inputEl,
    sendBtnEl,
  };
}
