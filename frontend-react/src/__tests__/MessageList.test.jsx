import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MessageList from "../components/MessageList";

function buildStreamMessage({ id, requestId, status, answer }) {
  return {
    id,
    requestId,
    role: "assistant_stream",
    status,
    search: { state: "hidden", query: "", results: [], error: "" },
    usageLines: [],
    reasoning: "",
    answer,
  };
}

describe("MessageList typing indicator", () => {
  it("shows typing only for streaming message with matching requestId", () => {
    const messages = [
      buildStreamMessage({ id: "m1", requestId: "req-1", status: "failed", answer: "Error: boom" }),
      buildStreamMessage({ id: "m2", requestId: "req-1", status: "streaming", answer: "Thinking..." }),
      buildStreamMessage({ id: "m3", requestId: "req-2", status: "streaming", answer: "Thinking..." }),
    ];

    render(<MessageList messages={messages} isPending={true} currentRequestId="req-1" />);

    expect(screen.getAllByLabelText("Typing")).toHaveLength(1);
    const failedNode = screen.getByText("Error: boom").closest(".msg.assistant.stream");
    expect(failedNode?.querySelector(".typing-dots")).toBeNull();
  });

  it("does not show typing for failed message even when requestId matches", () => {
    const messages = [buildStreamMessage({ id: "m1", requestId: "req-1", status: "failed", answer: "Error: failed" })];

    render(<MessageList messages={messages} isPending={true} currentRequestId="req-1" />);

    expect(screen.queryByLabelText("Typing")).toBeNull();
    const failedNode = within(screen.getByTestId("messages-list")).getByText("Error: failed").closest(".msg.assistant.stream");
    expect(failedNode?.querySelector(".typing-dots")).toBeNull();
  });
});
