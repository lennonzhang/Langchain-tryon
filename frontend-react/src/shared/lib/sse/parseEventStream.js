export async function parseEventStream(reader, onEvent) {
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      return;
    }

    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    let splitAt = buffer.indexOf("\n\n");
    while (splitAt >= 0) {
      const block = buffer.slice(0, splitAt).trim();
      buffer = buffer.slice(splitAt + 2);
      splitAt = buffer.indexOf("\n\n");
      if (!block) {
        continue;
      }

      for (const line of block.split("\n")) {
        if (!line.startsWith("data:")) {
          continue;
        }
        const payload = line.slice(5).trim();
        let event;
        try {
          event = JSON.parse(payload);
        } catch {
          continue;
        }

        await Promise.resolve(onEvent(event));
        if (event?.type === "done") {
          await reader.cancel();
          return event;
        }
      }
    }
  }
}
