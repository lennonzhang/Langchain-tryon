import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseEventStream } from "../shared/lib/sse/parseEventStream";

class FixtureReader {
  constructor(text, chunkSize = text.length) {
    const encoder = new TextEncoder();
    this.chunks = [];
    for (let i = 0; i < text.length; i += chunkSize) {
      this.chunks.push(encoder.encode(text.slice(i, i + chunkSize)));
    }
    this.index = 0;
    this.cancelled = false;
  }

  async read() {
    if (this.index >= this.chunks.length) {
      return { done: true, value: undefined };
    }
    const value = this.chunks[this.index];
    this.index += 1;
    return { done: false, value };
  }

  async cancel() {
    this.cancelled = true;
  }
}

function fixture(name) {
  const path = resolve(process.cwd(), "tests/fixtures/sse", name);
  return readFileSync(path, "utf-8");
}

describe("parseEventStream fixtures", () => {
  it("handles malformed lines without interrupting stream", async () => {
    const reader = new FixtureReader(fixture("stream-malformed-lines.txt"), 7);
    const events = [];

    await parseEventStream(reader, (evt) => events.push(evt));

    expect(events).toEqual([{ type: "token", content: "ok" }, { type: "done" }]);
    expect(reader.cancelled).toBe(true);
  });

  it("parses error then done sequence", async () => {
    const reader = new FixtureReader(fixture("stream-error-then-done.txt"));
    const events = [];

    await parseEventStream(reader, (evt) => events.push(evt));

    expect(events).toEqual([
      { type: "error", error: "boom" },
      { type: "done", finish_reason: "error" },
    ]);
  });

  it("keeps order with async handlers on fixture stream", async () => {
    const reader = new FixtureReader(fixture("stream-error-then-done.txt"), 5);
    const order = [];

    await parseEventStream(reader, async (evt) => {
      order.push(`start:${evt.type}`);
      await new Promise((resolve) => setTimeout(resolve, evt.type === "error" ? 10 : 1));
      order.push(`end:${evt.type}`);
    });

    expect(order).toEqual([
      "start:error",
      "end:error",
      "start:done",
      "end:done",
    ]);
  });
});
