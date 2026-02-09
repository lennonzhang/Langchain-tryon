import { createDOMRefs } from "./dom.js";
import { createMessageView } from "./messages.js";

export function createUI() {
  const refs = createDOMRefs();
  const view = createMessageView(refs.messagesEl);

  function setPending(isPending) {
    refs.sendBtnEl.disabled = isPending;
    refs.inputEl.disabled = isPending;
  }

  return {
    ...refs,
    ...view,
    setPending,
  };
}
