import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemorySessionRepository } from "../entities/session/memorySessionRepository";

describe("MemorySessionRepository", () => {
  let repo;

  beforeEach(() => {
    repo = new MemorySessionRepository();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00.000Z"));
  });

  it("supports create, append, list, get and delete", async () => {
    await repo.createSession({
      id: "s1",
      title: "A",
      settings: { model: "moonshotai/kimi-k2.5", webSearch: false, thinkingMode: true },
    });

    await repo.appendMessages("s1", [{ id: "u1", role: "user", content: "hello" }]);

    const detail = await repo.getSession("s1");
    expect(detail.messages).toHaveLength(1);

    const list = await repo.listSessions();
    expect(list).toHaveLength(1);
    expect(list[0].title).toBe("A");

    await repo.deleteSession("s1");
    expect(await repo.listSessions()).toHaveLength(0);
  });

  it("sorts list by updatedAt desc", async () => {
    await repo.createSession({
      id: "s1",
      title: "A",
      settings: { model: "moonshotai/kimi-k2.5", webSearch: false, thinkingMode: true },
    });

    vi.setSystemTime(new Date("2026-01-01T00:01:00.000Z"));
    await repo.createSession({
      id: "s2",
      title: "B",
      settings: { model: "qwen/qwen3.5-397b-a17b", webSearch: true, thinkingMode: true },
    });

    const firstOrder = await repo.listSessions();
    expect(firstOrder.map((item) => item.id)).toEqual(["s2", "s1"]);

    vi.setSystemTime(new Date("2026-01-01T00:02:00.000Z"));
    await repo.appendMessages("s1", [{ id: "u1", role: "user", content: "bump" }]);

    const secondOrder = await repo.listSessions();
    expect(secondOrder.map((item) => item.id)).toEqual(["s1", "s2"]);
  });

  it("updates message atomically under interleaving updates", async () => {
    await repo.createSession({
      id: "s1",
      title: "A",
      settings: { model: "moonshotai/kimi-k2.5", webSearch: false, thinkingMode: true },
    });

    await repo.appendMessages("s1", [
      {
        id: "m1",
        role: "assistant_stream",
        status: "streaming",
        search: { state: "hidden", query: "", results: [], error: "" },
        usageLines: [],
        reasoning: "",
        answer: "Thinking...",
      },
    ]);

    await Promise.all([
      repo.updateMessage("s1", "m1", (msg) => ({ ...msg, reasoning: `${msg.reasoning}a` })),
      repo.updateMessage("s1", "m1", (msg) => ({ ...msg, answer: "done" })),
    ]);

    const detail = await repo.getSession("s1");
    const msg = detail.messages[0];
    expect(msg.answer).toBe("done");
    expect(msg.reasoning).toContain("a");
  });
});
