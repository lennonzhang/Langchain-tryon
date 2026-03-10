import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App, { shortModelName } from "../App";
import { useChatUiStore } from "../shared/store/chatUiStore";
import { MemorySessionRepository } from "../entities/session/memorySessionRepository";

const fetchCapabilities = vi.fn();
const streamChat = vi.fn();
const cancelChat = vi.fn();

vi.mock("../shared/api/chatApiClient", () => ({
  fetchCapabilities: (...args) => fetchCapabilities(...args),
  streamChat: (...args) => streamChat(...args),
  cancelChat: (...args) => cancelChat(...args),
}));

const CAPABILITIES_RESPONSE = {
  version: 1,
  default: "moonshotai/kimi-k2.5",
  models: [
    { id: "moonshotai/kimi-k2.5", label: "Kimi K2.5", capabilities: { thinking: true, media: true, agent: false }, context_window: 131072 },
    { id: "qwen/qwen3.5-397b-a17b", label: "Qwen 3.5", capabilities: { thinking: true, media: false, agent: true }, context_window: 128000 },
    { id: "qwen/qwen3.5-122b-a10b", label: "Qwen 3.5 122B", capabilities: { thinking: true, media: false, agent: true }, context_window: 262144 },
  ],
};

let mediaQueryEnv;
let resizeObserverEnv;

function mockPendingAbortableStream({ emitDoneOnAbort = false } = {}) {
  let handlersRef = null;

  streamChat.mockImplementationOnce(async (_payload, handlers, options = {}) => {
    handlersRef = handlers;
    await new Promise((_, reject) => {
      const signal = options.signal;
      if (!signal) return;
      const abortError = () => signal.reason ?? new DOMException("Aborted", "AbortError");
      if (signal.aborted) {
        reject(abortError());
        return;
      }
      signal.addEventListener(
        "abort",
        () => {
          if (emitDoneOnAbort) {
            handlers.onEvent?.({ type: "done", finish_reason: "stop" });
            handlers.onDone?.();
          }
          reject(abortError());
        },
        { once: true },
      );
    });
  });

  return {
    getHandlers: () => handlersRef,
  };
}

function attachScrollMetrics(element, { scrollHeight = 0, clientHeight = 0, scrollTop = 0 } = {}) {
  let currentScrollHeight = scrollHeight;
  let currentClientHeight = clientHeight;
  let currentScrollTop = scrollTop;

  Object.defineProperty(element, "scrollHeight", {
    configurable: true,
    get: () => currentScrollHeight,
    set: (value) => {
      currentScrollHeight = value;
    },
  });

  Object.defineProperty(element, "clientHeight", {
    configurable: true,
    get: () => currentClientHeight,
    set: (value) => {
      currentClientHeight = value;
    },
  });

  Object.defineProperty(element, "scrollTop", {
    configurable: true,
    get: () => currentScrollTop,
    set: (value) => {
      currentScrollTop = value;
    },
  });

  return {
    setMetrics(next) {
      if (typeof next.scrollHeight === "number") currentScrollHeight = next.scrollHeight;
      if (typeof next.clientHeight === "number") currentClientHeight = next.clientHeight;
      if (typeof next.scrollTop === "number") currentScrollTop = next.scrollTop;
    },
    readScrollTop() {
      return currentScrollTop;
    },
  };
}

function installMatchMedia(initialMatches = false) {
  let matches = initialMatches;
  const listeners = new Set();
  const media = "(max-width: 600px)";
  const mediaQueryList = {
    media,
    get matches() {
      return matches;
    },
    onchange: null,
    addListener: vi.fn((listener) => listeners.add(listener)),
    removeListener: vi.fn((listener) => listeners.delete(listener)),
    addEventListener: vi.fn((event, listener) => {
      if (event === "change") listeners.add(listener);
    }),
    removeEventListener: vi.fn((event, listener) => {
      if (event === "change") listeners.delete(listener);
    }),
    dispatchEvent: vi.fn(),
  };

  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => mediaQueryList),
  });

  return {
    setMatches(nextMatches) {
      matches = nextMatches;
      const event = { matches, media };
      mediaQueryList.onchange?.(event);
      listeners.forEach((listener) => listener(event));
    },
  };
}

function installResizeObserver() {
  class MockResizeObserver {
    static instances = [];

    constructor(callback) {
      this.callback = callback;
      this.observe = vi.fn();
      this.unobserve = vi.fn();
      this.disconnect = vi.fn();
      MockResizeObserver.instances.push(this);
    }
  }

  global.ResizeObserver = MockResizeObserver;

  return {
    trigger(targets) {
      const entries = targets.map((target) => ({
        target,
        contentRect: target.getBoundingClientRect?.() || { width: target.offsetWidth || 0 },
      }));

      MockResizeObserver.instances.forEach((instance) => instance.callback(entries, instance));
    },
  };
}

function setElementWidth(element, width) {
  Object.defineProperty(element, "offsetWidth", {
    configurable: true,
    get: () => width,
  });

  element.getBoundingClientRect = () => ({
    width,
    height: 0,
    top: 0,
    left: 0,
    right: width,
    bottom: 0,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
}

describe("App behavior (session v2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatUiStore.getState().reset();
    mediaQueryEnv = installMatchMedia(false);
    resizeObserverEnv = installResizeObserver();
    fetchCapabilities.mockResolvedValue(CAPABILITIES_RESPONSE);
    cancelChat.mockResolvedValue({ cancelled: true });
    streamChat.mockImplementation(async (_payload, handlers) => {
      handlers.onEvent({ type: "token", content: "final answer" });
      handlers.onEvent({ type: "done" });
      handlers.onDone?.();
    });

    class MockFileReader {
      readAsDataURL(file) {
        this.result = `data:${file.type};base64,ZmFrZQ==`;
        setTimeout(() => this.onload?.(), 0);
      }
    }
    global.FileReader = MockFileReader;
    global.URL.createObjectURL = vi.fn(() => "blob:mock");
    global.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete global.ResizeObserver;
  });

  async function findComposerInput() {
    // Placeholder changes when another session is streaming, so match flexibly.
    await waitFor(() => expect(document.getElementById("input")).toBeTruthy());
    return document.getElementById("input");
  }

  it("exports shortModelName helper", () => {
    expect(shortModelName("qwen/qwen3.5-397b-a17b")).toBe("qwen3.5-397b-a17b");
  });

  it("creates first session and updates summary from assistant response", async () => {
    render(<App />);

    const input = await findComposerInput();
    await userEvent.type(input, "hello from first session");
    fireEvent.submit(document.querySelector("form.composer"));

    expect(await screen.findByText("final answer")).toBeInTheDocument();
    const list = await screen.findByTestId("session-list");
    expect(list.textContent).toContain("hello from first session");
    expect(list.textContent).toContain("final answer");
  });

  it("opens sessions sidebar from chat header button in narrow overlay mode", async () => {
    render(<App />);

    const appShell = document.querySelector(".app-shell");
    const sidebar = document.getElementById("session-sidebar");
    setElementWidth(appShell, 840);
    setElementWidth(sidebar, 320);
    act(() => {
      resizeObserverEnv.trigger([appShell, sidebar]);
    });

    await waitFor(() => expect(appShell).toHaveClass("is-session-overlay"));
    expect(sidebar?.classList.contains("is-open")).toBe(false);

    const trigger = screen.getByRole("button", { name: "Open sessions panel" });
    expect(trigger).toHaveAttribute("aria-controls", "session-sidebar");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(trigger);

    expect(sidebar?.classList.contains("is-open")).toBe(true);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("exits narrow overlay mode after the shell widens again", async () => {
    render(<App />);

    const appShell = document.querySelector(".app-shell");
    const sidebar = document.getElementById("session-sidebar");
    setElementWidth(appShell, 840);
    setElementWidth(sidebar, 320);
    act(() => {
      resizeObserverEnv.trigger([appShell, sidebar]);
    });

    await waitFor(() => expect(appShell).toHaveClass("is-session-overlay"));
    await userEvent.click(screen.getByRole("button", { name: "Open sessions panel" }));
    expect(sidebar).toHaveClass("is-open");

    setElementWidth(appShell, 980);
    act(() => {
      resizeObserverEnv.trigger([appShell, sidebar]);
    });

    await waitFor(() => expect(appShell).not.toHaveClass("is-session-overlay"));
    await waitFor(() => expect(sidebar).not.toHaveClass("is-open"));
  });

  it("keeps overlay mode stable across repeated resize notifications at the same narrow width", async () => {
    render(<App />);

    const appShell = document.querySelector(".app-shell");
    const sidebar = document.getElementById("session-sidebar");
    setElementWidth(appShell, 840);
    setElementWidth(sidebar, 320);

    act(() => {
      resizeObserverEnv.trigger([appShell, sidebar]);
      resizeObserverEnv.trigger([appShell, sidebar]);
      resizeObserverEnv.trigger([appShell, sidebar]);
    });

    await waitFor(() => expect(appShell).toHaveClass("is-session-overlay"));
  });

  it("enters overlay mode at the exact width threshold", async () => {
    render(<App />);

    const appShell = document.querySelector(".app-shell");
    const sidebar = document.getElementById("session-sidebar");
    setElementWidth(appShell, 864);
    setElementWidth(sidebar, 320);

    act(() => {
      resizeObserverEnv.trigger([appShell, sidebar]);
    });

    await waitFor(() => expect(appShell).toHaveClass("is-session-overlay"));
  });

  it("uses the same overlay sidebar mode on true mobile viewports", async () => {
    mediaQueryEnv.setMatches(true);
    render(<App />);

    const appShell = document.querySelector(".app-shell");
    const sidebar = document.getElementById("session-sidebar");

    await waitFor(() => expect(appShell).toHaveClass("is-session-overlay"));
    await userEvent.click(screen.getByRole("button", { name: "Open sessions panel" }));

    expect(sidebar).toHaveClass("is-open");
    expect(screen.getByRole("button", { name: "Open sessions panel" })).toHaveAttribute("aria-expanded", "true");
  });

  it("fallback capabilities include qwen 122b and keep attachments hidden for it", async () => {
    fetchCapabilities.mockRejectedValueOnce(new Error("capabilities down"));

    render(<App />);

    await userEvent.click(screen.getByRole("button", { name: /kimi-k2\.5/i }));
    await userEvent.click(screen.getByText("qwen3.5-122b-a10b"));

    expect(screen.queryByTestId("attach-strip")).toBeNull();
  });

  it("new chat hides old messages, preserves unsent draft across switching, then clears it after first send", async () => {
    render(<App />);

    await userEvent.type(await findComposerInput(), "origin session message");
    fireEvent.submit(document.querySelector("form.composer"));

    const messageList = screen.getByTestId("messages-list");
    expect(await within(messageList).findByText("final answer")).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("New chat"));
    await waitFor(() => {
      expect(within(messageList).queryByText("final answer")).toBeNull();
      expect(within(messageList).getByText("Connected. Type your question to start.")).toBeInTheDocument();
    });

    await userEvent.type(await findComposerInput(), "draft keeps me");

    const sessionList = screen.getByTestId("session-list");
    const previousSessionTitle = within(sessionList).getByText("origin session message");
    const previousSessionButton = previousSessionTitle.closest(".session-item");
    expect(previousSessionButton).toBeTruthy();
    await userEvent.click(previousSessionButton);
    expect(await within(messageList).findByText("final answer")).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("New chat"));
    expect((await findComposerInput()).value).toContain("draft keeps me");

    fireEvent.submit(document.querySelector("form.composer"));
    await within(messageList).findByText("final answer");
    expect(streamChat).toHaveBeenCalledTimes(2);

    await userEvent.click(screen.getByLabelText("New chat"));
    expect((await findComposerInput()).value).toBe("");
  });

  it("preserves new chat draft when switching away immediately and typing in another session", async () => {
    render(<App />);

    await userEvent.type(await findComposerInput(), "origin session message");
    fireEvent.submit(document.querySelector("form.composer"));
    await screen.findByText("final answer");

    await userEvent.click(screen.getByLabelText("New chat"));
    await userEvent.type(await findComposerInput(), "draft A");

    const sessionList = screen.getByTestId("session-list");
    const previousSessionTitle = within(sessionList).getByText("origin session message");
    const previousSessionButton = previousSessionTitle.closest(".session-item");
    expect(previousSessionButton).toBeTruthy();

    await userEvent.click(previousSessionButton);
    await userEvent.type(await findComposerInput(), " more in old session");

    await userEvent.click(screen.getByLabelText("New chat"));
    expect((await findComposerInput()).value).toBe("draft A");
  });

  it("keeps error UI when stream emits error then done", async () => {
    streamChat.mockImplementationOnce(async (_payload, handlers) => {
      handlers.onEvent({ type: "error", error: "boom" });
      handlers.onEvent({ type: "done", finish_reason: "error" });
      handlers.onDone?.();
    });

    render(<App />);
    await userEvent.type(await findComposerInput(), "hello");
    fireEvent.submit(document.querySelector("form.composer"));

    expect(await screen.findByText("Error: boom")).toBeInTheDocument();
  });

  it("shows typing only for current streaming message after a previous failed message", async () => {
    streamChat
      .mockImplementationOnce(async (_payload, handlers) => {
        handlers.onEvent({ type: "error", error: "boom" });
        handlers.onEvent({ type: "done", finish_reason: "error" });
        handlers.onDone?.();
      })
      .mockImplementationOnce(async () => {});

    render(<App />);
    const input = await findComposerInput();

    await userEvent.type(input, "first question");
    fireEvent.submit(document.querySelector("form.composer"));
    expect(await screen.findByText("Error: boom")).toBeInTheDocument();

    await userEvent.clear(await findComposerInput());
    await userEvent.type(await findComposerInput(), "second question");
    fireEvent.submit(document.querySelector("form.composer"));

    await waitFor(() => {
      expect(document.querySelectorAll(".typing-dots")).toHaveLength(1);
    });

    const messageList = screen.getByTestId("messages-list");
    const failedMessageNode = within(messageList).getByText("Error: boom").closest(".msg.assistant.stream");
    expect(failedMessageNode?.querySelector(".typing-dots")).toBeNull();
  });

  it("folds previous reasoning and expands current reasoning for multi-turn in one session", async () => {
    streamChat.mockImplementationOnce(async (_payload, handlers) => {
      handlers.onEvent({ type: "reasoning", content: "First round reasoning" });
      handlers.onEvent({ type: "token", content: "first answer" });
      handlers.onEvent({ type: "done" });
      handlers.onDone?.();
    });
    const pending = mockPendingAbortableStream();

    render(<App />);
    const input = await findComposerInput();

    await userEvent.type(input, "first question");
    fireEvent.submit(document.querySelector("form.composer"));
    expect(await screen.findByText("first answer")).toBeInTheDocument();

    await userEvent.clear(await findComposerInput());
    await userEvent.type(await findComposerInput(), "second question");
    fireEvent.submit(document.querySelector("form.composer"));

    await waitFor(() => expect(pending.getHandlers()).toBeTruthy());
    await act(async () => {
      pending.getHandlers().onEvent({ type: "reasoning", content: "Second round reasoning" });
    });

    const messageList = screen.getByTestId("messages-list");
    const firstRound = within(messageList).getByText("first answer").closest(".msg.assistant.stream");
    const secondRound = within(messageList).getByText("Thinking...").closest(".msg.assistant.stream");
    expect(firstRound?.querySelector(".assistant-section.reasoning")).toHaveClass("is-closed");
    expect(secondRound?.querySelector(".assistant-section.reasoning")).toHaveClass("is-open");

    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    await screen.findByText("Ready");
  });

  it("resumes auto-follow after the user scrolls back to the bottom", async () => {
    const pending = mockPendingAbortableStream();
    const originalRaf = global.requestAnimationFrame;
    global.requestAnimationFrame = vi.fn((callback) => {
      callback(0);
      return 1;
    });

    try {
      render(<App />);
      const messageList = screen.getByTestId("messages-list");
      const metrics = attachScrollMetrics(messageList, {
        scrollHeight: 500,
        clientHeight: 200,
        scrollTop: 300,
      });

      await userEvent.type(await findComposerInput(), "scroll recovery");
      fireEvent.submit(document.querySelector("form.composer"));

      await waitFor(() => {
        expect(pending.getHandlers()).toBeTruthy();
        expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
      });
      expect(metrics.readScrollTop()).toBe(500);

      metrics.setMetrics({ scrollHeight: 650 });
      await act(async () => {
        pending.getHandlers().onEvent({ type: "token", content: "chunk one" });
      });
      expect(metrics.readScrollTop()).toBe(650);

      metrics.setMetrics({ scrollTop: 100 });
      fireEvent.scroll(messageList);

      metrics.setMetrics({ scrollHeight: 780 });
      await act(async () => {
        pending.getHandlers().onEvent({ type: "token", content: "chunk two" });
      });
      expect(metrics.readScrollTop()).toBe(100);

      metrics.setMetrics({ scrollTop: 580 });
      fireEvent.scroll(messageList);

      metrics.setMetrics({ scrollHeight: 900 });
      await act(async () => {
        pending.getHandlers().onEvent({ type: "token", content: "chunk three" });
      });
      expect(metrics.readScrollTop()).toBe(900);

      await userEvent.click(screen.getByRole("button", { name: "Stop" }));
      await screen.findByText("Ready");
    } finally {
      global.requestAnimationFrame = originalRaf;
    }
  });

  it("splits reasoning into paragraphs across agent steps during streaming", async () => {
    const pending = mockPendingAbortableStream();

    render(<App />);
    const input = await findComposerInput();
    await userEvent.type(input, "agent step formatting");
    fireEvent.submit(document.querySelector("form.composer"));

    await waitFor(() => expect(pending.getHandlers()).toBeTruthy());
    await act(async () => {
      pending.getHandlers().onEvent({ type: "agent_step_start", step: 1 });
      pending.getHandlers().onEvent({ type: "reasoning", content: "Planning data gathering steps" });
      pending.getHandlers().onEvent({ type: "agent_step_start", step: 2 });
      pending.getHandlers().onEvent({ type: "reasoning", content: "Planning targeted data search" });
    });

    const messageList = screen.getByTestId("messages-list");
    const streamNode = within(messageList).getByText("Thinking...").closest(".msg.assistant.stream");
    const reasoningPanel = within(streamNode).getByTestId("reasoning-panel");
    expect(reasoningPanel.querySelectorAll("p").length).toBeGreaterThanOrEqual(2);

    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    await screen.findByText("Ready");
  });

  it("blocks sending globally while another session is running", async () => {
    const pending = mockPendingAbortableStream();

    render(<App />);
    await userEvent.type(await findComposerInput(), "session one question");
    fireEvent.submit(document.querySelector("form.composer"));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
      expect(screen.getByText("Generating response...")).toBeInTheDocument();
    });

    await userEvent.click(screen.getByLabelText("New chat"));
    const nextInput = await findComposerInput();
    const sendBtn = screen.getByRole("button", { name: "Send" });

    expect(nextInput).toBeDisabled();
    expect(sendBtn).toBeDisabled();
    expect(screen.getByText("Response running in another session. Open it to stop.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
    expect(streamChat).toHaveBeenCalledTimes(1);

    const sessionList = screen.getByTestId("session-list");
    const runningSessionButton = sessionList.querySelector(".session-row:not(.session-row-entry) .session-item");
    expect(runningSessionButton).toBeTruthy();
    await userEvent.click(runningSessionButton);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    });

    await act(async () => {
      pending.getHandlers()?.onEvent({ type: "token", content: "still running" });
    });
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    await screen.findByText("Ready");
  });

  it("stop keeps partial answer and unlocks next send", async () => {
    const pending = mockPendingAbortableStream();

    render(<App />);
    await userEvent.type(await findComposerInput(), "first long question");
    fireEvent.submit(document.querySelector("form.composer"));

    await waitFor(() => {
      expect(pending.getHandlers()).toBeTruthy();
      expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    });

    await act(async () => {
      pending.getHandlers().onEvent({ type: "token", content: "partial answer" });
    });
    expect(screen.getByText("partial answer")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => {
      expect(screen.getByText("Ready")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
    });
    expect(screen.queryByText("Canceled by user.")).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("New chat"));
    const nextInput = await findComposerInput();
    expect(nextInput).not.toBeDisabled();
    await userEvent.type(nextInput, "second session question");
    fireEvent.submit(document.querySelector("form.composer"));

    expect(await screen.findByText("final answer")).toBeInTheDocument();
    expect(streamChat).toHaveBeenCalledTimes(2);
  });

  it("stop calls cancel endpoint for the active request", async () => {
    const pending = mockPendingAbortableStream();

    render(<App />);
    await userEvent.type(await findComposerInput(), "cancel request check");
    fireEvent.submit(document.querySelector("form.composer"));

    await waitFor(() => {
      expect(pending.getHandlers()).toBeTruthy();
      expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: "Stop" }));

    await waitFor(() => {
      expect(cancelChat).toHaveBeenCalledTimes(1);
    });
    expect(cancelChat.mock.calls[0][0]).toEqual(expect.any(String));
    expect(cancelChat.mock.calls[0][0].length).toBeGreaterThan(10);
  });

  it("stop without token stores canceled by user", async () => {
    mockPendingAbortableStream();

    render(<App />);
    await userEvent.type(await findComposerInput(), "empty cancel case");
    fireEvent.submit(document.querySelector("form.composer"));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    const messageList = screen.getByTestId("messages-list");
    expect(await within(messageList).findByText("Canceled by user.")).toBeInTheDocument();
  });

  it("done and abort race keeps first terminal outcome", async () => {
    const pending = mockPendingAbortableStream({ emitDoneOnAbort: true });

    render(<App />);
    await userEvent.type(await findComposerInput(), "race done abort");
    fireEvent.submit(document.querySelector("form.composer"));

    await waitFor(() => {
      expect(pending.getHandlers()).toBeTruthy();
      expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    });

    await act(async () => {
      pending.getHandlers().onEvent({ type: "token", content: "race-partial" });
    });

    await userEvent.click(screen.getByRole("button", { name: "Stop" }));

    const messageList = screen.getByTestId("messages-list");
    expect(await within(messageList).findByText("race-partial")).toBeInTheDocument();
    expect(within(messageList).queryByText("Canceled by user.")).toBeNull();
  });

  it("done and transport error race keeps first terminal outcome", async () => {
    streamChat.mockImplementationOnce(async (_payload, handlers) => {
      handlers.onEvent({ type: "token", content: "race-done-error" });
      handlers.onDone?.();
      throw new Error("transport boom");
    });

    render(<App />);
    await userEvent.type(await findComposerInput(), "race done transport error");
    fireEvent.submit(document.querySelector("form.composer"));

    const messageList = screen.getByTestId("messages-list");
    expect(await within(messageList).findByText("race-done-error")).toBeInTheDocument();
    expect(within(messageList).queryByText("Error: transport boom")).toBeNull();
  });

  it("releases pending lock when repository throws during finalization", async () => {
    streamChat.mockImplementationOnce(async (_payload, handlers) => {
      handlers.onEvent({ type: "token", content: "before-crash" });
      handlers.onEvent({ type: "done" });
      handlers.onDone?.();
    });

    const origUpdate = MemorySessionRepository.prototype.updateMessage;
    let callCount = 0;
    vi.spyOn(MemorySessionRepository.prototype, "updateMessage").mockImplementation(
      async function (...args) {
        callCount++;
        // First call patches the token event; second call is finalization — make it throw.
        if (callCount === 2) throw new Error("repo crash");
        return origUpdate.apply(this, args);
      },
    );

    render(<App />);
    await userEvent.type(await findComposerInput(), "repo fail test");
    fireEvent.submit(document.querySelector("form.composer"));

    // Pending lock should be released despite the repository error.
    await waitFor(() => {
      expect(screen.getByText("Ready")).toBeInTheDocument();
    });

    MemorySessionRepository.prototype.updateMessage.mockRestore();
  });

  it("prevents deleting a streaming session even when UI disable is bypassed", async () => {
    mockPendingAbortableStream();

    render(<App />);
    await userEvent.type(await findComposerInput(), "protect this session");
    fireEvent.submit(document.querySelector("form.composer"));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    });

    const sessionList = screen.getByTestId("session-list");
    const deleteBtn = within(sessionList).getByRole("button", { name: /^Delete/ });
    expect(deleteBtn).toBeDisabled();

    // Simulate bypassing disabled UI and clicking delete directly.
    deleteBtn.removeAttribute("disabled");
    await userEvent.click(deleteBtn);

    // Data-layer guard should still keep the running session intact.
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
    expect(within(screen.getByTestId("session-list")).getAllByRole("button", { name: /^Delete/ })).toHaveLength(1);
  });
});
