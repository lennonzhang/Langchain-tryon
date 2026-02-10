export function createDOMRefs() {
  const messagesEl = document.getElementById("messages");
  const formEl = document.getElementById("form");
  const inputEl = document.getElementById("input");
  const sendBtnEl = document.getElementById("sendBtn");
  const modelEl = document.getElementById("modelSelect");
  const searchToggleEl = document.getElementById("searchToggle");
  const thinkingToggleEl = document.getElementById("thinkingToggle");
  const thinkingToggleWrapEl = document.getElementById("thinkingToggleWrap");
  const imageInputEl = document.getElementById("imageInput");
  const imageInputWrapEl = document.getElementById("imageInputWrap");

  return {
    messagesEl,
    formEl,
    inputEl,
    sendBtnEl,
    modelEl,
    searchToggleEl,
    thinkingToggleEl,
    thinkingToggleWrapEl,
    imageInputEl,
    imageInputWrapEl,
  };
}
