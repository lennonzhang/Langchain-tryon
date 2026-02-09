import { bindChatComposer } from "./chat-controller.js";
import { createChatState } from "./state.js";
import { createUI } from "./ui.js";

const ui = createUI();
const state = createChatState();

bindChatComposer(ui, state);
