import { beforeEach, describe, expect, it } from "vitest";
import { QueryClient } from "../shared/vendor/react-query";
import { sessionDetailQueryKey } from "../features/sessions/useSessions";
import { mapStreamEventToPatch } from "../features/chat/mapStreamEventToPatch";

function buildSession(messages) {
  return {
    id: "s1",
    title: "Test",
    createdAt: "2025-01-01T00:00:00Z",
    updatedAt: "2025-01-01T00:00:00Z",
    settings: { model: "test" },
    messages,
  };
}

function buildStreamMessage(id, requestId, overrides = {}) {
  return {
    id,
    requestId,
    role: "assistant_stream",
    status: "streaming",
    search: { state: "hidden", query: "", results: [], error: "" },
    usageLines: [],
    reasoning: "",
    answer: "Thinking...",
    ...overrides,
  };
}

function patchStreamMessageInCache(queryClient, sessionId, streamId, event) {
  const prev = queryClient.getQueryData(sessionDetailQueryKey(sessionId));
  if (!prev) return;
  queryClient.setQueryData(sessionDetailQueryKey(sessionId), {
    ...prev,
    messages: prev.messages.map((msg) =>
      msg.id === streamId ? mapStreamEventToPatch(msg, event) : msg
    ),
  });
}

describe("patchStreamMessageInCache", () => {
  let queryClient;

  beforeEach(() => {
    queryClient = new QueryClient();
  });

  it("updates only the targeted stream message", () => {
    const msg1 = buildStreamMessage("m1", "req-1", { status: "done", answer: "First answer" });
    const msg2 = buildStreamMessage("m2", "req-2");
    const session = buildSession([msg1, msg2]);
    queryClient.setQueryData(sessionDetailQueryKey("s1"), session);

    patchStreamMessageInCache(queryClient, "s1", "m2", { type: "token", content: "Hello" });

    const updated = queryClient.getQueryData(sessionDetailQueryKey("s1"));
    expect(updated.messages[0].answer).toBe("First answer");
    expect(updated.messages[1].answer).toBe("Hello");
  });

  it("preserves object references for unchanged messages", () => {
    const msg1 = buildStreamMessage("m1", "req-1", { status: "done", answer: "Done" });
    const msg2 = buildStreamMessage("m2", "req-2");
    const session = buildSession([msg1, msg2]);
    queryClient.setQueryData(sessionDetailQueryKey("s1"), session);

    const before = queryClient.getQueryData(sessionDetailQueryKey("s1"));
    const msg1Before = before.messages[0];

    patchStreamMessageInCache(queryClient, "s1", "m2", { type: "token", content: "Hi" });

    const after = queryClient.getQueryData(sessionDetailQueryKey("s1"));
    expect(after.messages[0]).toBe(msg1Before);
    expect(after.messages[1]).not.toBe(before.messages[1]);
  });

  it("does nothing when cache has no data", () => {
    patchStreamMessageInCache(queryClient, "s1", "m1", { type: "token", content: "x" });
    expect(queryClient.getQueryData(sessionDetailQueryKey("s1"))).toBeUndefined();
  });

  it("accumulates multiple token events correctly", () => {
    const msg = buildStreamMessage("m1", "req-1");
    const session = buildSession([msg]);
    queryClient.setQueryData(sessionDetailQueryKey("s1"), session);

    patchStreamMessageInCache(queryClient, "s1", "m1", { type: "token", content: "Hello" });
    patchStreamMessageInCache(queryClient, "s1", "m1", { type: "token", content: " world" });

    const updated = queryClient.getQueryData(sessionDetailQueryKey("s1"));
    expect(updated.messages[0].answer).toBe("Hello world");
  });

  it("handles done event setting status to done", () => {
    const msg = buildStreamMessage("m1", "req-1");
    const session = buildSession([msg]);
    queryClient.setQueryData(sessionDetailQueryKey("s1"), session);

    patchStreamMessageInCache(queryClient, "s1", "m1", { type: "token", content: "Answer" });
    patchStreamMessageInCache(queryClient, "s1", "m1", { type: "done" });

    const updated = queryClient.getQueryData(sessionDetailQueryKey("s1"));
    expect(updated.messages[0].status).toBe("done");
    expect(updated.messages[0].answer).toBe("Answer");
  });
});
