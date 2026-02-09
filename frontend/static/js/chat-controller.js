import { streamChat } from "./api.js";

export function bindChatComposer(ui, state) {
  ui.addMessage("assistant", "已连接。请输入你的问题。");
  ui.inputEl.focus();

  ui.formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = ui.inputEl.value.trim();
    if (!text) return;

    ui.inputEl.value = "";
    ui.setPending(true);

    ui.addMessage("user", text);
    const pending = ui.addMessage("assistant", "思考中...");

    let answer = "";

    try {
      await streamChat({
        message: text,
        history: state.snapshot(),
        onEvent: (evt) => {
          if (evt.type === "token") {
            answer += evt.content || "";
            ui.updateMessage(pending, answer || "思考中...");
            return;
          }

          if (evt.type === "error") {
            throw new Error(evt.error || "流式请求失败");
          }
        },
      });

      if (!answer) {
        ui.updateMessage(pending, "(空响应)");
      }

      state.appendTurn(text, answer);
    } catch (err) {
      ui.updateMessage(pending, `错误: ${err.message}`);
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
