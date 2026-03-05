import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App, { shortModelName } from "../App";
import { useChatUiStore } from "../shared/store/chatUiStore";
import { MemorySessionRepository } from "../entities/session/memorySessionRepository";

const fetchCapabilities = vi.fn();
const streamChat = vi.fn();

vi.mock("../shared/api/chatApiClient", () => ({
  fetchCapabilities: (...args) => fetchCapabilities(...args),
  streamChat: (...args) => streamChat(...args),
}));

const CAPABILITIES_RESPONSE = {
  version: 1,
  default: "moonshotai/kimi-k2.5",
  models: [
    { id: "moonshotai/kimi-k2.5", label: "Kimi K2.5", capabilities: { thinking: true, media: true, agent: false }, context_window: 131072 },
    { id: "qwen/qwen3.5-397b-a17b", label: "Qwen 3.5", capabilities: { thinking: true, media: false, agent: true }, context_window: 128000 },
  ],
};

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

describe("App behavior (session v2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatUiStore.getState().reset();
    fetchCapabilities.mockResolvedValue(CAPABILITIES_RESPONSE);
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

  it("opens sessions sidebar from chat header button", async () => {
    render(<App />);

    const sidebar = document.getElementById("session-sidebar");
    expect(sidebar?.classList.contains("is-open")).toBe(false);

    const trigger = screen.getByRole("button", { name: "Open sessions panel" });
    expect(trigger).toHaveAttribute("aria-controls", "session-sidebar");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(trigger);

    expect(sidebar?.classList.contains("is-open")).toBe(true);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("new chat hides old messages, preserves unsent draft across switching, then clears it after first send", async () => {
    render(<App />);

    await userEvent.type(await findComposerInput(), "origin session message");
    fireEvent.submit(document.querySelector("form.composer"));

    const messageList = screen.getByTestId("messages-list");
    expect(await within(messageList).findByText("final answer")).toBeInTheDocument();

    await userEvent.click(screen.getByText("+ New Chat"));
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

    await userEvent.click(screen.getByText("+ New Chat"));
    expect((await findComposerInput()).value).toContain("draft keeps me");

    fireEvent.submit(document.querySelector("form.composer"));
    await within(messageList).findByText("final answer");
    expect(streamChat).toHaveBeenCalledTimes(2);

    await userEvent.click(screen.getByText("+ New Chat"));
    expect((await findComposerInput()).value).toBe("");
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

    await userEvent.click(screen.getByText("+ New Chat"));
    const nextInput = await findComposerInput();
    const sendBtn = screen.getByRole("button", { name: "Send" });

    expect(nextInput).toBeDisabled();
    expect(sendBtn).toBeDisabled();
    expect(screen.getByText("Response running in another session. Open it to stop.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
    expect(streamChat).toHaveBeenCalledTimes(1);

    const sessionList = screen.getByTestId("session-list");
    const runningSessionButton = sessionList.querySelector(".session-item");
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

    await userEvent.click(screen.getByText("+ New Chat"));
    const nextInput = await findComposerInput();
    expect(nextInput).not.toBeDisabled();
    await userEvent.type(nextInput, "second session question");
    fireEvent.submit(document.querySelector("form.composer"));

    expect(await screen.findByText("final answer")).toBeInTheDocument();
    expect(streamChat).toHaveBeenCalledTimes(2);
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
