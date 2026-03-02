import { beforeEach, describe, expect, it } from "vitest";
import { NEW_SESSION_KEY, useChatUiStore } from "../shared/store/chatUiStore";

describe("chatUiStore", () => {
  beforeEach(() => {
    useChatUiStore.getState().reset();
  });

  it("isolates draft by session id", () => {
    const store = useChatUiStore.getState();
    store.setDraft("s1", "hello");
    store.setDraft("s2", "world");
    store.setDraft(null, "new");

    expect(store.getDraft("s1")).toBe("hello");
    expect(store.getDraft("s2")).toBe("world");
    expect(useChatUiStore.getState().draftsBySessionId[NEW_SESSION_KEY]).toBe("new");
  });

  it("tracks pending lifecycle and errors", () => {
    const store = useChatUiStore.getState();
    store.startRequest("s1", "r1");

    expect(useChatUiStore.getState().pendingBySessionId.s1).toBe(true);
    expect(useChatUiStore.getState().isCurrentRequest("s1", "r1")).toBe(true);

    store.finishRequest("s1");
    expect(useChatUiStore.getState().pendingBySessionId.s1).toBe(false);

    store.startRequest("s1", "r2");
    store.failRequest("s1", "boom");
    expect(useChatUiStore.getState().lastErrorBySessionId.s1).toBe("boom");
    expect(useChatUiStore.getState().pendingBySessionId.s1).toBe(false);
  });

  it("rejects stale request id", () => {
    const store = useChatUiStore.getState();
    store.startRequest("s1", "r1");
    store.startRequest("s1", "r2");

    expect(useChatUiStore.getState().isCurrentRequest("s1", "r1")).toBe(false);
    expect(useChatUiStore.getState().isCurrentRequest("s1", "r2")).toBe(true);
  });
});
