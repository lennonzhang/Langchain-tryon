import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App, { shortModelName } from "../App";
import { useChatUiStore } from "../shared/store/chatUiStore";

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

  async function findComposerInput() {
    return screen.findByPlaceholderText("Press Enter to send (Shift+Enter for newline)");
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

  it("isolates streams across sessions", async () => {
    let firstHandlers;
    streamChat
      .mockImplementationOnce(async (_payload, handlers) => {
        firstHandlers = handlers;
      })
      .mockImplementationOnce(async (_payload, handlers) => {
        handlers.onEvent({ type: "token", content: "second-session-answer" });
        handlers.onEvent({ type: "done" });
        handlers.onDone?.();
      });

    render(<App />);
    const input = await findComposerInput();

    await userEvent.type(input, "session one question");
    fireEvent.submit(document.querySelector("form.composer"));

    await userEvent.click(screen.getByText("+ New Chat"));
    const freshInput = await findComposerInput();
    await userEvent.type(freshInput, "session two question");
    fireEvent.submit(document.querySelector("form.composer"));

    await screen.findByText("second-session-answer");

    await act(async () => {
      firstHandlers.onEvent({ type: "token", content: "first-session-answer" });
      firstHandlers.onEvent({ type: "done" });
      firstHandlers.onDone?.();
    });

    await waitFor(() => {
      const list = screen.getByTestId("session-list");
      expect(list.textContent).toContain("first-session-answer");
      expect(list.textContent).toContain("second-session-answer");
    });
  });
});
