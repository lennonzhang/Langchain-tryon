import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ensurePrismLoadedMock = vi.hoisted(() => vi.fn());

vi.mock("../utils/prism-loader", () => ({
  ensurePrismLoaded: ensurePrismLoadedMock,
}));

import RichBlock from "../components/RichBlock";

describe("RichBlock", () => {
  let writeTextMock;

  beforeEach(() => {
    ensurePrismLoadedMock.mockReset();
    ensurePrismLoadedMock.mockResolvedValue(undefined);
    writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: writeTextMock },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    delete window.Prism;
  });

  it("renders copy button for fenced code blocks", () => {
    render(<RichBlock className="assistant-body" text={"```js\nconst x = 1;\n```"} />);
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
  });

  it("copies code via delegated handler and resets button text", async () => {
    vi.useFakeTimers();
    render(<RichBlock className="assistant-body" text={"```js\nconst x = 1;\n```"} />);
    const button = screen.getByRole("button", { name: "Copy" });

    await act(async () => {
      fireEvent.click(button);
      await Promise.resolve();
    });

    expect(screen.getByRole("button", { name: "Copied!" })).toBeInTheDocument();
    expect(writeTextMock).toHaveBeenCalledWith(expect.stringContaining("const x = 1;"));

    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
  });

  it("skips Prism highlighting while streaming and runs once after completion", async () => {
    const highlightElement = vi.fn();
    window.Prism = { highlightElement };

    const { rerender } = render(
      <RichBlock className="assistant-body" text={"```js\nconst x = 1;\n```"} streaming={true} />,
    );

    expect(highlightElement).not.toHaveBeenCalled();

    rerender(<RichBlock className="assistant-body" text={"```js\nconst x = 1;\n```"} streaming={false} />);

    await waitFor(() => {
      expect(highlightElement).toHaveBeenCalledTimes(1);
    });
  });

  it("lazy-loads Prism when code exists and Prism is missing", async () => {
    const highlightElement = vi.fn();
    ensurePrismLoadedMock.mockImplementation(async () => {
      window.Prism = { highlightElement };
    });
    delete window.Prism;

    render(<RichBlock className="assistant-body" text={"```js\nconst x = 1;\n```"} streaming={false} />);

    await waitFor(() => {
      expect(ensurePrismLoadedMock).toHaveBeenCalledTimes(1);
      expect(highlightElement).toHaveBeenCalledTimes(1);
    });
  });
});
