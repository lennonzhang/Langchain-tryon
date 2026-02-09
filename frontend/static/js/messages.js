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

    // Search section (hidden by default, shown when web search is active)
    const searchSection = document.createElement("div");
    searchSection.className = "assistant-section search";
    searchSection.style.display = "none";

    const searchTitle = document.createElement("div");
    searchTitle.className = "assistant-title";
    searchTitle.textContent = "Search";

    const searchBody = document.createElement("div");
    searchBody.className = "assistant-body";

    searchSection.appendChild(searchTitle);
    searchSection.appendChild(searchBody);

    // Reasoning section
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

    // Answer section
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

    root.appendChild(searchSection);
    root.appendChild(reasoningSection);
    root.appendChild(answerSection);

    messagesEl.appendChild(root);
    scrollToBottom();

    return {
      root,
      searchSection,
      searchBody,
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

  function updateAssistantSearchStart(target, query) {
    target.searchSection.style.display = "block";
    target.searchBody.innerHTML = `<span class="search-loading">\u6b63\u5728\u641c\u7d22: \u201c${esc(query)}\u201d\u2026</span>`;
    scrollToBottom();
  }

  function updateAssistantSearchDone(target, results) {
    if (!results || results.length === 0) {
      target.searchBody.innerHTML = '<span class="search-empty">\u672a\u627e\u5230\u76f8\u5173\u7ed3\u679c</span>';
      scrollToBottom();
      return;
    }
    const items = results
      .map((r, i) => {
        const title = esc(r.title || r.url);
        const snippet = r.snippet
          ? `<div class="search-snippet">${esc(r.snippet)}</div>`
          : "";
        return `<div class="search-item">[${i + 1}] <a href="${esc(r.url)}" target="_blank" rel="noopener">${title}</a>${snippet}</div>`;
      })
      .join("");
    target.searchBody.innerHTML = `<div class="search-results">${items}</div>`;
    scrollToBottom();
  }

  function updateAssistantSearchError(target, errorMessage) {
    target.searchSection.style.display = "block";
    target.searchBody.innerHTML = `<span class="search-error">\u641c\u7d22\u5931\u8d25: ${esc(errorMessage)}</span>`;
    scrollToBottom();
  }

  function esc(input) {
    return String(input)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  return {
    addMessage,
    updateMessage,
    addAssistantStreamMessage,
    updateAssistantReasoning,
    updateAssistantAnswer,
    setAssistantStreamError,
    updateAssistantSearchStart,
    updateAssistantSearchDone,
    updateAssistantSearchError,
  };
}