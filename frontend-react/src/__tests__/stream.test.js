import { parseEventStream } from "../stream";

class FakeReader {
  constructor(chunks) {
    this.chunks = chunks.map((chunk) => new TextEncoder().encode(chunk));
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

describe("parseEventStream", () => {
  it("parses multiple events and stops at done", async () => {
    const events = [];
    const reader = new FakeReader([
      'data: {"type":"token","content":"Hello"}\n\n',
      'data: {"type":"token","content":" world"}\n\n',
      'data: {"type":"done","finish_reason":"stop"}\n\n',
      'data: {"type":"token","content":"ignored"}\n\n',
    ]);

    await parseEventStream(reader, (evt) => events.push(evt));

    expect(events).toEqual([
      { type: "token", content: "Hello" },
      { type: "token", content: " world" },
      { type: "done", finish_reason: "stop" },
    ]);
    expect(reader.cancelled).toBe(true);
  });

  it("ignores malformed JSON and non-data lines", async () => {
    const events = [];
    const reader = new FakeReader([
      "event: custom\n",
      "data: {not-json}\n\n",
      'data: {"type":"token","content":"ok"}\n\n',
      'data: {"type":"done"}\n\n',
    ]);

    await parseEventStream(reader, (evt) => events.push(evt));

    expect(events).toEqual([{ type: "token", content: "ok" }, { type: "done" }]);
  });

  it("handles chunk boundaries across event blocks", async () => {
    const events = [];
    const reader = new FakeReader([
      'data: {"type":"token","content":"A',
      'B"}\n\ndata: {"type":"done"}\n\n',
    ]);

    await parseEventStream(reader, (evt) => events.push(evt));

    expect(events).toEqual([{ type: "token", content: "AB" }, { type: "done" }]);
  });
});
