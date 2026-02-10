export function createDOMRefs() {
  const messagesEl = document.getElementById("messages");
  const formEl = document.getElementById("form");
  const inputEl = document.getElementById("input");
  const sendBtnEl = document.getElementById("sendBtn");
  const modelEl = document.getElementById("modelSelect");
  const searchToggleEl = document.getElementById("searchToggle");
  const thinkingToggleEl = document.getElementById("thinkingToggle");
  const thinkingToggleWrapEl = document.getElementById("thinkingToggleWrap");
  const imagePickerBtnEl = document.getElementById("imagePickerBtn");
  const imageCountBadgeEl = document.getElementById("imageCountBadge");
  const imageInputEl = document.getElementById("imageInput");

  return {
    messagesEl,
    formEl,
    inputEl,
    sendBtnEl,
    modelEl,
    searchToggleEl,
    thinkingToggleEl,
    thinkingToggleWrapEl,
    imagePickerBtnEl,
    imageCountBadgeEl,
    imageInputEl,
  };
}
