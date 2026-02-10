import { createDOMRefs } from "./dom.js";
import { createMessageView } from "./messages.js";

export function createUI() {
  const refs = createDOMRefs();
  const view = createMessageView(refs.messagesEl);

  function setPending(isPending) {
    refs.sendBtnEl.disabled = isPending;
    refs.inputEl.disabled = isPending;
    if (refs.modelEl) {
      refs.modelEl.disabled = isPending;
    }
    if (refs.searchToggleEl) {
      refs.searchToggleEl.disabled = isPending;
    }
    if (refs.thinkingToggleEl) {
      refs.thinkingToggleEl.disabled = isPending;
    }
    if (refs.imageInputEl) {
      refs.imageInputEl.disabled = isPending;
    }
  }

  return {
    ...refs,
    ...view,
    setPending,
  };
}
