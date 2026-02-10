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

    const searchSection = createSection("search", "Search");
    searchSection.section.style.display = "none";

    const usageSection = createSection("usage", "Context Usage");
    usageSection.section.style.display = "none";

    const reasoningSection = createSection("reasoning", "Reasoning");
    reasoningSection.section.style.display = "none";

    const answerSection = createSection("answer", "Answer");
    answerSection.body.textContent = "Thinking...";

    root.appendChild(searchSection.section);
    root.appendChild(usageSection.section);
    root.appendChild(reasoningSection.section);
    root.appendChild(answerSection.section);

    messagesEl.appendChild(root);
    scrollToBottom();

    return {
      root,
      searchSection: searchSection.section,
      searchBody: searchSection.body,
      usageSection: usageSection.section,
      usageBody: usageSection.body,
      reasoningSection: reasoningSection.section,
      reasoningBody: reasoningSection.body,
      answerSection: answerSection.section,
      answerBody: answerSection.body,
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
    target.answerBody.textContent = `Error: ${errorMessage}`;
    scrollToBottom();
  }

  function updateAssistantSearchStart(target, query) {
    target.searchSection.style.display = "block";
    target.searchBody.innerHTML = `<span class="search-loading">正在搜索: “${esc(query)}”...</span>`;
    scrollToBottom();
  }

  function updateAssistantSearchDone(target, results) {
    target.searchSection.style.display = "block";
    if (!results || results.length === 0) {
      target.searchBody.innerHTML = '<span class="search-empty">未找到相关结果</span>';
      scrollToBottom();
      return;
    }
    const items = results
      .map((r, i) => {
        const title = esc(r.title || r.url);
        const snippet = r.snippet ? `<div class="search-snippet">${esc(r.snippet)}</div>` : "";
        return `<div class="search-item">[${i + 1}] <a href="${esc(r.url)}" target="_blank" rel="noopener">${title}</a>${snippet}</div>`;
      })
      .join("");
    target.searchBody.innerHTML = `<div class="search-results">${items}</div>`;
    scrollToBottom();
  }

  function updateAssistantSearchError(target, errorMessage) {
    target.searchSection.style.display = "block";
    target.searchBody.innerHTML = `<span class="search-error">搜索失败: ${esc(errorMessage)}</span>`;
    scrollToBottom();
  }

  function updateAssistantContextUsage(target, usage) {
    target.usageSection.style.display = "block";
    const phase = esc(usage?.phase || "unknown");
    const model = esc(usage?.model || "");
    const used = Number(usage?.used_estimated_tokens || 0);
    const total = Number(usage?.window_total_tokens || 0);
    const ratio = Number(usage?.usage_ratio || 0);
    const pct = (ratio * 100).toFixed(2);
    const line = `<div class="agent-loading">[${phase}] ${used}/${total} tokens (${pct}%) ${model ? `- ${model}` : ""}</div>`;
    target.usageBody.innerHTML += line;
    scrollToBottom();
  }

  function createSection(kind, title) {
    const section = document.createElement("div");
    section.className = `assistant-section ${kind}`;

    const titleEl = document.createElement("div");
    titleEl.className = "assistant-title";
    titleEl.textContent = title;

    const body = document.createElement("div");
    body.className = "assistant-body";

    section.appendChild(titleEl);
    section.appendChild(body);
    return { section, body };
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
    updateAssistantContextUsage,
  };
}
