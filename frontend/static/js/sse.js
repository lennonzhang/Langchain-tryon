export async function parseEventStream(reader, onEvent) {
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!block) continue;

      const lines = block.split("\n");
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();

        let event;
        try {
          event = JSON.parse(payload);
        } catch {
          // Ignore malformed payload from SSE stream.
          continue;
        }

        // Do not swallow caller errors (e.g. server-side error event).
        onEvent(event);

        // Some servers keep the connection open after done; end read proactively.
        if (event?.type === "done") {
          await reader.cancel();
          return;
        }
      }
    }
  }
}
