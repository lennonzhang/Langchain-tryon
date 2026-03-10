import { describe, expect, it } from "vitest";
import { mapStreamEventToPatch, mergeReasoningChunk } from "../features/chat/mapStreamEventToPatch";

function baseMessage() {
  return {
    id: "m1",
    role: "assistant_stream",
    status: "streaming",
    search: { state: "hidden", query: "", results: [], error: "" },
    usageLines: [],
    reasoning: "",
    reasoningStepCursor: 0,
    reasoningNeedsStepBreak: false,
    finishReason: null,
    clarification: null,
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

  it("adds a space between merged alphanumeric chunks", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "ratios" });
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "Planning targeted data search" });
    expect(msg.reasoning).toBe("ratios Planning targeted data search");
  });

  it("adds a paragraph break before markdown block starts", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "Assessing data sufficiency" });
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "****Planning data retrieval and estimation" });
    expect(msg.reasoning).toBe("Assessing data sufficiency\n\n****Planning data retrieval and estimation");
  });

  it("splits step-like reasoning chunks into separate paragraphs", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "Planning data gathering steps" });
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "Planning deeper data search" });
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "Reporting insufficient data availability" });

    expect(msg.reasoning).toBe(
      "Planning data gathering steps\n\nPlanning deeper data search\n\nReporting insufficient data availability",
    );
  });

  it("inserts paragraph break between reasoning chunks when step advances", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, { type: "agent_step_start", step: 1 });
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "Planning data gathering steps" });
    msg = mapStreamEventToPatch(msg, { type: "agent_step_start", step: 2 });
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "Planning targeted data search" });
    expect(msg.reasoning).toBe("Planning data gathering steps\n\nPlanning targeted data search");
  });

  it("does not add duplicate paragraph breaks for repeated step events", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, { type: "agent_step_start", step: 1 });
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "Planning data gathering steps" });
    msg = mapStreamEventToPatch(msg, { type: "agent_step_start", step: 2 });
    msg = mapStreamEventToPatch(msg, { type: "agent_step_start", step: 2 });
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "Planning targeted data search" });
    expect(msg.reasoning).toBe("Planning data gathering steps\n\nPlanning targeted data search");
    expect(msg.reasoning.includes("\n\n\n\n")).toBe(false);
  });

  it("splits sticky step keywords within a single chunk", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, {
      type: "reasoning",
      content: "Planning data gathering stepsPlanning targeted data search",
    });
    expect(msg.reasoning).toBe("Planning data gathering steps\n\nPlanning targeted data search");
  });

  it("splits sticky markdown block starts within a single chunk", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, {
      type: "reasoning",
      content: "Summarizing income data limitations****Confirming data insufficiency",
    });
    expect(msg.reasoning).toBe("Summarizing income data limitations\n\n****Confirming data insufficiency");
  });

  it("keeps existing whitespace/newline without extra insertion", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "line-1\n" });
    msg = mapStreamEventToPatch(msg, { type: "reasoning", content: "line-2" });
    expect(msg.reasoning).toBe("line-1\nline-2");
  });

  it("overrides usage lines when phase is final", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, {
      type: "context_usage",
      usage: {
        phase: "single",
        used_estimated_tokens: 100,
        window_total_tokens: 1000,
        usage_ratio: 0.1,
      },
    });
    msg = mapStreamEventToPatch(msg, {
      type: "context_usage",
      usage: {
        phase: "final",
        used_estimated_tokens: 220,
        window_total_tokens: 1000,
        usage_ratio: 0.22,
      },
    });

    expect(msg.usageLines).toHaveLength(1);
    expect(msg.usageLines[0]).toContain("[final] 220/1000 tokens (22.00%)");
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

  it("stores clarification metadata for user input requests", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, {
      type: "user_input_required",
      question: "Which environment should I use?",
      options: [
        { id: "staging", label: "staging", description: "Safer rollout" },
        { id: "prod", label: "production" },
      ],
      allow_free_text: false,
    });

    expect(msg.answer).toBe("Which environment should I use?");
    expect(msg.clarification).toEqual({
      question: "Which environment should I use?",
      options: [
        { id: "staging", label: "staging", description: "Safer rollout" },
        { id: "prod", label: "production", description: "" },
      ],
      allowFreeText: false,
      answered: false,
    });
  });

  it("done event preserves question text in answer when clarification exists", () => {
    let msg = baseMessage();
    msg = mapStreamEventToPatch(msg, {
      type: "user_input_required",
      question: "Which env?",
      options: [],
    });
    expect(msg.answer).toBe("Which env?");
    msg = mapStreamEventToPatch(msg, { type: "done", finish_reason: "user_input_required" });
    expect(msg.answer).toBe("Which env?");
    expect(msg.status).toBe("done");
  });
});

describe("mergeReasoningChunk", () => {
  it("does not force spaces between CJK chunks", () => {
    expect(mergeReasoningChunk("\u4E2D\u6587", "\u7EE7\u7EED")).toBe("\u4E2D\u6587\u7EE7\u7EED");
  });
});
