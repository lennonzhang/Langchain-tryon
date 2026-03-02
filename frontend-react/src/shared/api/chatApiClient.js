import { parseEventStream } from "../lib/sse/parseEventStream";

export async function fetchCapabilities() {
  const resp = await fetch("/api/capabilities");
  if (!resp.ok) {
    throw new Error("Failed to load capabilities");
  }
  return resp.json();
}

export async function streamChat(payload, handlers) {
  const resp = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    let detail = "Request failed";
    try {
      const body = await resp.json();
      detail = body.error || detail;
    } catch {
      // no-op
    }
    throw new Error(detail);
  }

  if (!resp.body) {
    throw new Error("Browser does not support streaming");
  }

  const reader = resp.body.getReader();

  await parseEventStream(reader, (event) => handlers.onEvent?.(event));

  handlers.onDone?.();
}
