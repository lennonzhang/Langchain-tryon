import { describe, expect, it } from "vitest";
import { mapStreamEventToPatch } from "../features/chat/mapStreamEventToPatch";

function baseMessage() {
  return {
    id: "m1",
    role: "assistant_stream",
    status: "streaming",
    search: { state: "hidden", query: "", results: [], error: "" },
    usageLines: [],
    reasoning: "",
    answer: "Thinking...",
  };
}

describe("mapStreamEventToPatch", () => {
  it("maps search events", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, { type: "search_start", query: "qwen" });
    expect(msg.search).toEqual({ state: "loading", query: "qwen", results: [], error: "" });

    msg = mapStreamEventToPatch(msg, {
      type: "search_done",
      results: [{ title: "R1", url: "https://a.com" }],
    });
    expect(msg.search.state).toBe("done");
    expect(msg.search.results).toHaveLength(1);

    msg = mapStreamEventToPatch(msg, { type: "search_error", error: "oops" });
    expect(msg.search).toEqual({ state: "error", query: "qwen", results: [], error: "oops" });
  });

  it("maps context usage and reasoning", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, {
      type: "context_usage",
      usage: {
        phase: "single",
        used_estimated_tokens: 100,
        window_total_tokens: 1000,
        usage_ratio: 0.1,
        model: "moonshotai/kimi-k2.5",
      },
    });
    expect(msg.usageLines[0]).toContain("[single] 100/1000 tokens (10.00%) - moonshotai/kimi-k2.5");

    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "step-1" });
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: " step-2" });
    expect(msg.reasoning).toBe("step-1 step-2");
  });

  it("accumulates token chunks and finalizes done", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, { type: "token", content: "Hello" });
    msg = mapStreamEventToPatch(msg, { type: "token", content: " world" });
    expect(msg.answer).toBe("Hello world");

    msg = mapStreamEventToPatch(msg, { type: "done" });
    expect(msg.status).toBe("done");
    expect(msg.answer).toBe("Hello world");
  });

  it("keeps empty fallback when no token before done", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, { type: "done" });
    expect(msg.status).toBe("done");
    expect(msg.answer).toBe("(empty response)");
  });

  it("keeps failed state after error then done", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, { type: "error", error: "boom" });
    expect(msg.status).toBe("failed");
    expect(msg.answer).toBe("Error: boom");

    msg = mapStreamEventToPatch(msg, { type: "done", finish_reason: "error" });
    expect(msg.status).toBe("failed");
    expect(msg.answer).toBe("Error: boom");
  });
});
