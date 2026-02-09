import { streamChat } from "./api.js";

export function bindChatComposer(ui, state) {
  ui.addMessage("assistant", "Connected. Ask your question.");
  ui.inputEl.focus();

  ui.formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = ui.inputEl.value.trim();
    if (!text) return;

    const model = ui.modelEl?.value || "moonshotai/kimi-k2.5";

    ui.inputEl.value = "";
    ui.setPending(true);

    ui.addMessage("user", `[${model}]\n${text}`);
    const pending = ui.addAssistantStreamMessage();

    let answer = "";
    let reasoning = "";

    try {
      await streamChat({
        message: text,
        history: state.snapshot(),
        model,
        onEvent: (evt) => {
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