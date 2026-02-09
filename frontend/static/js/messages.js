import { renderRichText } from "./render.js";

export function createMessageView(messagesEl) {
  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addMessage(role, content) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;

    if (role === "assistant") {
      renderRichText(div, content);
    } else {
      div.textContent = content;
    }

    messagesEl.appendChild(div);
    scrollToBottom();
    return div;
  }

  function updateMessage(el, content) {
    if (el.classList.contains("assistant")) {
      renderRichText(el, content);
    } else {
      el.textContent = content;
    }
    scrollToBottom();
  }

  function addAssistantStreamMessage() {
    const root = document.createElement("div");
    root.className = "msg assistant stream";

    const reasoningSection = document.createElement("div");
    reasoningSection.className = "assistant-section reasoning";
    reasoningSection.style.display = "none";

    const reasoningTitle = document.createElement("div");
    reasoningTitle.className = "assistant-title";
    reasoningTitle.textContent = "Reasoning";

    const reasoningBody = document.createElement("div");
    reasoningBody.className = "assistant-body";

    reasoningSection.appendChild(reasoningTitle);
    reasoningSection.appendChild(reasoningBody);

    const answerSection = document.createElement("div");
    answerSection.className = "assistant-section answer";

    const answerTitle = document.createElement("div");
    answerTitle.className = "assistant-title";
    answerTitle.textContent = "Answer";

    const answerBody = document.createElement("div");
    answerBody.className = "assistant-body";
    answerBody.textContent = "Thinking...";

    answerSection.appendChild(answerTitle);
    answerSection.appendChild(answerBody);

    root.appendChild(reasoningSection);
    root.appendChild(answerSection);

    messagesEl.appendChild(root);
    scrollToBottom();

    return {
      root,
      reasoningSection,
      reasoningBody,
      answerSection,
      answerBody,
    };
  }

  function updateAssistantReasoning(target, reasoning) {
    if (!reasoning) {
      target.reasoningSection.style.display = "none";
      target.reasoningBody.textContent = "";
      return;
    }

    target.reasoningSection.style.display = "block";
    renderRichText(target.reasoningBody, reasoning);
    scrollToBottom();
  }

  function updateAssistantAnswer(target, answer) {
    renderRichText(target.answerBody, answer || "Thinking...");
    scrollToBottom();
  }

  function setAssistantStreamError(target, errorMessage) {
    target.reasoningSection.style.display = "none";
    target.answerBody.textContent = `Error: ${errorMessage}`;
    scrollToBottom();
  }

  return {
    addMessage,
    updateMessage,
    addAssistantStreamMessage,
    updateAssistantReasoning,
    updateAssistantAnswer,
    setAssistantStreamError,
  };
}