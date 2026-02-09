export function createDOMRefs() {
  const messagesEl = document.getElementById("messages");
  const formEl = document.getElementById("form");
  const inputEl = document.getElementById("input");
  const sendBtnEl = document.getElementById("sendBtn");
  const modelEl = document.getElementById("modelSelect");

  return {
    messagesEl,
    formEl,
    inputEl,
    sendBtnEl,
    modelEl,
  };
}