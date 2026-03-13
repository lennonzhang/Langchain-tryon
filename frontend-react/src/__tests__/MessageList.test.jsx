import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MessageList from "../components/MessageList";
import { CONNECTED_TEXT } from "../utils/models";

function buildStreamMessage({ id, requestId, status, answer, reasoning = "" }) {
  return {
    id,
    requestId,
    role: "assistant_stream",
    status,
    search: { state: "hidden", query: "", results: [], error: "" },
    usageLines: [],
    reasoning,
    answer,
  };
}

describe("MessageList typing indicator", () => {
  it("renders the new-chat placeholder synchronously without markdown warmup", () => {
    const messages = [{ id: "connected", role: "assistant", content: CONNECTED_TEXT }];

    render(<MessageList messages={messages} isPending={false} currentRequestId={null} />);

    expect(screen.getByText(CONNECTED_TEXT)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy" })).toBeNull();
  });

  it("shows typing only for streaming message with matching requestId", async () => {
    const messages = [
      buildStreamMessage({ id: "m1", requestId: "req-1", status: "failed", answer: "Error: boom" }),
      buildStreamMessage({ id: "m2", requestId: "req-1", status: "streaming", answer: "Thinking..." }),
      buildStreamMessage({ id: "m3", requestId: "req-2", status: "streaming", answer: "Thinking..." }),
    ];

    render(<MessageList messages={messages} isPending={true} currentRequestId="req-1" />);

    await screen.findByText("Error: boom");
    expect(screen.getAllByLabelText("Typing")).toHaveLength(1);
    const failedNode = screen.getByText("Error: boom").closest(".msg.assistant.stream");
    expect(failedNode?.querySelector(".typing-dots")).toBeNull();
  });

  it("does not show typing for failed message even when requestId matches", async () => {
    const messages = [buildStreamMessage({ id: "m1", requestId: "req-1", status: "failed", answer: "Error: failed" })];

    render(<MessageList messages={messages} isPending={true} currentRequestId="req-1" />);

    await screen.findByText("Error: failed");
    expect(screen.queryByLabelText("Typing")).toBeNull();
    const failedNode = within(screen.getByTestId("messages-list")).getByText("Error: failed").closest(".msg.assistant.stream");
    expect(failedNode?.querySelector(".typing-dots")).toBeNull();
  });

  it("does not show typing for completed messages when a new request is streaming", async () => {
    const messages = [
      buildStreamMessage({ id: "m1", requestId: "req-1", status: "done", answer: "First answer" }),
      buildStreamMessage({ id: "m2", requestId: "req-2", status: "streaming", answer: "Thinking..." }),
    ];

    render(<MessageList messages={messages} isPending={true} currentRequestId="req-2" />);

    await screen.findByText("First answer");
    const typingElements = screen.getAllByLabelText("Typing");
    expect(typingElements).toHaveLength(1);

    const firstAnswer = screen.getByText("First answer").closest(".msg.assistant.stream");
    expect(firstAnswer?.querySelector(".typing-dots")).toBeNull();
  });

  it("does not show typing for completed messages across multiple turns", async () => {
    const messages = [
      buildStreamMessage({ id: "m1", requestId: "req-1", status: "done", answer: "Answer 1" }),
      buildStreamMessage({ id: "m2", requestId: "req-2", status: "done", answer: "Answer 2" }),
      buildStreamMessage({ id: "m3", requestId: "req-3", status: "streaming", answer: "Thinking..." }),
    ];

    render(<MessageList messages={messages} isPending={true} currentRequestId="req-3" />);

    await screen.findByText("Answer 1");
    expect(screen.getAllByLabelText("Typing")).toHaveLength(1);

    const answer1 = screen.getByText("Answer 1").closest(".msg.assistant.stream");
    const answer2 = screen.getByText("Answer 2").closest(".msg.assistant.stream");
    expect(answer1?.querySelector(".typing-dots")).toBeNull();
    expect(answer2?.querySelector(".typing-dots")).toBeNull();
  });

  it("applies stream-done class only to completed stream messages", async () => {
    const messages = [
      buildStreamMessage({ id: "m1", requestId: "req-1", status: "done", answer: "Done answer" }),
      buildStreamMessage({ id: "m2", requestId: "req-2", status: "streaming", answer: "Streaming..." }),
    ];

    render(<MessageList messages={messages} isPending={true} currentRequestId="req-2" />);

    await screen.findByText("Done answer");
    const doneMsg = screen.getByText("Done answer").closest(".msg.assistant.stream");
    const streamingMsg = screen.getByText("Streaming...").closest(".msg.assistant.stream");

    expect(doneMsg?.classList.contains("stream-done")).toBe(true);
    expect(streamingMsg?.classList.contains("stream-done")).toBe(false);
  });

  it("expands current request reasoning and folds previous rounds in same session", async () => {
    const messages = [
      buildStreamMessage({
        id: "m1",
        requestId: "req-1",
        status: "done",
        answer: "Answer 1",
        reasoning: "Reasoning 1",
      }),
      buildStreamMessage({
        id: "m2",
        requestId: "req-2",
        status: "streaming",
        answer: "Thinking...",
        reasoning: "Reasoning 2",
      }),
    ];

    render(<MessageList messages={messages} isPending={true} currentRequestId="req-2" />);

    await screen.findByText("Answer 1");
    const round1 = screen.getByText("Answer 1").closest(".msg.assistant.stream");
    const round2 = screen.getByText("Thinking...").closest(".msg.assistant.stream");
    expect(round1?.querySelector(".assistant-section.reasoning")).toHaveClass("is-closed");
    expect(round2?.querySelector(".assistant-section.reasoning")).toHaveClass("is-open");
  });

  it("keeps latest round reasoning expanded when stream finishes", async () => {
    const messages = [
      buildStreamMessage({
        id: "m1",
        requestId: "req-1",
        status: "done",
        answer: "Answer 1",
        reasoning: "Reasoning 1",
      }),
      buildStreamMessage({
        id: "m2",
        requestId: "req-2",
        status: "done",
        answer: "Answer 2",
        reasoning: "Reasoning 2",
      }),
    ];

    render(<MessageList messages={messages} isPending={false} currentRequestId={null} />);

    await screen.findByText("Answer 1");
    const round1 = screen.getByText("Answer 1").closest(".msg.assistant.stream");
    const round2 = screen.getByText("Answer 2").closest(".msg.assistant.stream");
    expect(round1?.querySelector(".assistant-section.reasoning")).toHaveClass("is-closed");
    expect(round2?.querySelector(".assistant-section.reasoning")).toHaveClass("is-open");
  });
});
