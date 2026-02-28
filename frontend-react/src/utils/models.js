export const CONNECTED_TEXT = "Connected. Type your question to start.";

export const FALLBACK_CAPABILITIES = {
  version: 1,
  default: "moonshotai/kimi-k2.5",
  models: [
    { id: "moonshotai/kimi-k2.5", label: "Kimi K2.5", capabilities: { thinking: true, media: true, agent: false }, context_window: 131072 },
    { id: "qwen/qwen3.5-397b-a17b", label: "Qwen 3.5", capabilities: { thinking: true, media: false, agent: true }, context_window: 128000 },
    { id: "z-ai/glm5", label: "GLM 5", capabilities: { thinking: true, media: false, agent: true }, context_window: 128000 },
  ],
};

export function shortModelName(model) {
  const idx = model.lastIndexOf("/");
  return idx >= 0 ? model.slice(idx + 1) : model;
}
