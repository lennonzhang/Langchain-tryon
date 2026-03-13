import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { __resetMarkdownStateForTests, __setMarkdownLoaderForTests } from "../utils/markdown";

const ensurePrismLoadedMock = vi.hoisted(() => vi.fn());

vi.mock("../utils/prism-loader", () => ({
  ensurePrismLoaded: ensurePrismLoadedMock,
}));

import RichBlock from "../components/RichBlock";

describe("RichBlock", () => {
  let writeTextMock;

  beforeEach(() => {
    __resetMarkdownStateForTests();
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
    __resetMarkdownStateForTests();
  });

  it("renders plain text immediately before markdown finishes loading", () => {
    render(<RichBlock className="assistant-body" text="**cold start**" />);

    expect(screen.getByText("**cold start**")).toBeInTheDocument();
  });

  it("keeps plain text visible if markdown loading fails", async () => {
    __setMarkdownLoaderForTests(() => Promise.reject(new Error("chunk failed")));

    const { container } = render(<RichBlock className="assistant-body" text="**still visible**" />);

    expect(screen.getByText("**still visible**")).toBeInTheDocument();

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText("**still visible**")).toBeInTheDocument();
    expect(container.querySelector("strong")).toBeNull();
  });

  it("renders copy button for fenced code blocks after markdown loads", async () => {
    render(<RichBlock className="assistant-body" text={"```js\nconst x = 1;\n```"} />);
    expect(await screen.findByRole("button", { name: "Copy" })).toBeInTheDocument();
  });

  it("copies code via delegated handler and resets button text", async () => {
    render(<RichBlock className="assistant-body" text={"```js\nconst x = 1;\n```"} />);
    const button = await screen.findByRole("button", { name: "Copy" });

    // Switch to fake timers after async rendering completes
    vi.useFakeTimers();

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
