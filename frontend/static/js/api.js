export async function streamChat({
  message,
  history,
  model,
  webSearch,
  thinkingMode,
  images,
  onEvent,
}) {
  const resp = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      history,
      model,
      web_search: webSearch || false,
      thinking_mode: thinkingMode ?? true,
      images: Array.isArray(images) ? images : [],
    }),
  });

  if (!resp.ok) {
    let detail = "请求失败";
    try {
      const err = await resp.json();
      detail = err.error || detail;
    } catch {
      // Keep generic message when response is not JSON.
    }
    throw new Error(detail);
  }

  if (!resp.body) {
    throw new Error("浏览器不支持流式读取");
  }

  const reader = resp.body.getReader();
  const { parseEventStream } = await import("./sse.js");
  await parseEventStream(reader, onEvent);
}
