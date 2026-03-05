import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StreamMessage from "../components/StreamMessage";

function buildMessage({
  id = "m1",
  searchState = "loading",
  query = "qwen",
  results = [],
  error = "",
  reasoning = "",
  answer = "answer",
} = {}) {
  return {
    id,
    role: "assistant_stream",
    requestId: "req-1",
    status: "streaming",
    search: { state: searchState, query, results, error },
    usageLines: [],
    reasoning,
    answer,
  };
}

describe("StreamMessage search collapse behavior", () => {
  it("re-mounts search panel collapsed when state changes from loading to done", () => {
    const { container, rerender } = render(
      <StreamMessage msg={buildMessage({ searchState: "loading" })} showTyping={false} />,
    );

    let searchSection = container.querySelector(".assistant-section.search");
    expect(searchSection).toHaveClass("is-open");

    rerender(<StreamMessage msg={buildMessage({ searchState: "done" })} showTyping={false} />);

    searchSection = container.querySelector(".assistant-section.search");
    expect(searchSection).toHaveClass("is-closed");
  });

  it("preserves user toggle when search state does not change", () => {
    const { container, rerender } = render(
      <StreamMessage msg={buildMessage({ searchState: "done" })} showTyping={false} />,
    );

    let searchSection = container.querySelector(".assistant-section.search");
    expect(searchSection).toHaveClass("is-closed");

    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    searchSection = container.querySelector(".assistant-section.search");
    expect(searchSection).toHaveClass("is-open");

    rerender(
      <StreamMessage
        msg={buildMessage({ searchState: "done", answer: "updated answer" })}
        showTyping={false}
      />,
    );

    searchSection = container.querySelector(".assistant-section.search");
    expect(searchSection).toHaveClass("is-open");
  });
});

describe("StreamMessage reasoning collapse behavior", () => {
  it("opens reasoning for current request message", () => {
    const { container } = render(
      <StreamMessage
        msg={buildMessage({ searchState: "hidden", reasoning: "current reasoning" })}
        showTyping={false}
        isCurrentRequestMessage={true}
      />,
    );

    const reasoningSection = container.querySelector(".assistant-section.reasoning");
    expect(reasoningSection).toHaveClass("is-open");
  });

  it("re-mounts reasoning collapsed when message becomes historical", () => {
    const { container, rerender } = render(
      <StreamMessage
        msg={buildMessage({ searchState: "hidden", reasoning: "reasoning body" })}
        showTyping={false}
        isCurrentRequestMessage={true}
      />,
    );

    let reasoningSection = container.querySelector(".assistant-section.reasoning");
    expect(reasoningSection).toHaveClass("is-open");

    rerender(
      <StreamMessage
        msg={buildMessage({ searchState: "hidden", reasoning: "reasoning body" })}
        showTyping={false}
        isCurrentRequestMessage={false}
      />,
    );

    reasoningSection = container.querySelector(".assistant-section.reasoning");
    expect(reasoningSection).toHaveClass("is-closed");
  });
});
