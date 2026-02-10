import { streamChat } from "./api.js";

export function bindChatComposer(ui, state) {
  ui.addMessage("assistant", "Connected. Ask your question.");
  ui.inputEl.focus();

  syncModelSpecificControls(ui);
  ui.modelEl?.addEventListener("change", () => syncModelSpecificControls(ui));

  ui.formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = ui.inputEl.value.trim();
    if (!text) return;

    const model = ui.modelEl?.value || "moonshotai/kimi-k2.5";
    const webSearch = ui.searchToggleEl?.checked || false;
    const supportsThinking = modelSupportsThinking(model);
    const supportsImageInput = modelSupportsImageInput(model);
    const thinkingMode = supportsThinking ? ui.thinkingToggleEl?.checked !== false : true;
    const images = supportsImageInput
      ? await readImageInputAsDataUrls(ui.imageInputEl)
      : [];

    ui.inputEl.value = "";
    ui.setPending(true);

    const tags = [model];
    if (webSearch) tags.push("Search");
    if (supportsThinking) {
      tags.push(thinkingMode ? "Thinking" : "Instant");
    }
    if (supportsImageInput) {
      if (images.length > 0) {
        tags.push(`Img x${images.length}`);
      }
    }
    const label = `[${tags.join("] [")}]\n${text}`;
    ui.addMessage("user", label);
    const pending = ui.addAssistantStreamMessage();

    let answer = "";
    let reasoning = "";

    try {
      await streamChat({
        message: text,
        history: state.snapshot(),
        model,
        webSearch,
        thinkingMode,
        images,
        onEvent: (evt) => {
          if (evt.type === "search_start") {
            ui.updateAssistantSearchStart(pending, evt.query);
            return;
          }
          if (evt.type === "search_done") {
            ui.updateAssistantSearchDone(pending, evt.results);
            return;
          }
          if (evt.type === "search_error") {
            ui.updateAssistantSearchError(pending, evt.error);
            return;
          }
          if (evt.type === "context_usage") {
            ui.updateAssistantContextUsage(pending, evt.usage);
            return;
          }
          if (evt.type === "reasoning") {
            reasoning += evt.content || "";
            ui.updateAssistantReasoning(pending, reasoning);
            return;
          }
          if (evt.type === "token") {
            answer += evt.content || "";
            ui.updateAssistantAnswer(pending, answer);
            return;
          }
          if (evt.type === "error") {
            throw new Error(evt.error || "Streaming request failed");
          }
        },
      });

      if (!answer) {
        answer = "(empty response)";
        ui.updateAssistantAnswer(pending, answer);
      }

      state.appendTurn(text, answer);
      if (ui.imageInputEl) {
        ui.imageInputEl.value = "";
      }
    } catch (err) {
      ui.setAssistantStreamError(pending, err.message);
    } finally {
      ui.setPending(false);
      ui.inputEl.focus();
    }
  });

  ui.inputEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      ui.formEl.requestSubmit();
    }
  });
}

function syncModelSpecificControls(ui) {
  const model = ui.modelEl?.value || "";
  const supportsThinking = modelSupportsThinking(model);
  const supportsImageInput = modelSupportsImageInput(model);
  if (ui.thinkingToggleWrapEl) {
    ui.thinkingToggleWrapEl.style.display = supportsThinking ? "inline-flex" : "none";
  }
  if (ui.imageInputWrapEl) {
    ui.imageInputWrapEl.style.display = supportsImageInput ? "flex" : "none";
  }
  if (ui.thinkingToggleEl) {
    ui.thinkingToggleEl.checked = supportsThinking ? ui.thinkingToggleEl.checked : true;
  }
  if (!supportsImageInput && ui.imageInputEl) {
    ui.imageInputEl.value = "";
  }
}

function modelSupportsThinking(model) {
  return model.startsWith("moonshotai/") || model.startsWith("z-ai/");
}

function modelSupportsImageInput(model) {
  return model.startsWith("moonshotai/");
}

async function readImageInputAsDataUrls(inputEl) {
  if (!inputEl?.files?.length) {
    return [];
  }

  const files = Array.from(inputEl.files).slice(0, 3);
  const reads = files.map(
    (file) =>
      new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
        reader.onerror = () => reject(new Error(`Failed to read image: ${file.name}`));
        reader.readAsDataURL(file);
      })
  );

  const results = await Promise.all(reads);
  return results.filter(Boolean);
}
