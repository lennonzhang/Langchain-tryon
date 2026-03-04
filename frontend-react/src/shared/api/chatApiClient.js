import { parseEventStream } from "../lib/sse/parseEventStream";

export async function fetchCapabilities() {
  const resp = await fetch("/api/capabilities");
  if (!resp.ok) {
    throw new Error("Failed to load capabilities");
  }
  return resp.json();
}

export async function streamChat(payload, handlers, { signal } = {}) {
  const resp = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!resp.ok) {
    let detail = "Request failed";
    try {
      const body = await resp.json();
      detail = body.error || detail;
    } catch (e) {
      if (e?.name === "AbortError") throw e;
    }
    throw new Error(`${resp.status} ${detail}`);
  }

  if (!resp.body) {
    throw new Error("Browser does not support streaming");
  }

  const reader = resp.body.getReader();

  await parseEventStream(reader, (event) => handlers.onEvent?.(event));

  await Promise.resolve(handlers.onDone?.());
}
