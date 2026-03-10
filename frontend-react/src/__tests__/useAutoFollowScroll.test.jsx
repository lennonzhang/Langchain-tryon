import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAutoFollowScroll } from "../hooks/useAutoFollowScroll";

function Harness({ tick, extraContent = false }) {
  const { containerRef, handleScroll } = useAutoFollowScroll({
    thresholdPx: 150,
    watchValue: tick,
  });

  return (
    <div data-testid="messages-list" ref={containerRef} onScroll={handleScroll}>
      <div>base content</div>
      {extraContent && <div>async rendered content</div>}
    </div>
  );
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

describe("useAutoFollowScroll", () => {
  let originalRaf;

  beforeEach(() => {
    originalRaf = global.requestAnimationFrame;
    global.requestAnimationFrame = vi.fn((callback) => {
      callback(0);
      return 1;
    });
  });

  afterEach(() => {
    global.requestAnimationFrame = originalRaf;
  });

  it("scrolls to bottom when the viewport was already near the bottom before new content arrives", () => {
    const view = render(<Harness tick={0} />);
    const list = screen.getByTestId("messages-list");
    const metrics = attachScrollMetrics(list, {
      scrollHeight: 500,
      clientHeight: 200,
      scrollTop: 300,
    });

    fireEvent.scroll(list);

    metrics.setMetrics({ scrollHeight: 650 });
    view.rerender(<Harness tick={1} />);

    expect(metrics.readScrollTop()).toBe(650);
  });

  it("does not force scroll when the user has moved away from the bottom", () => {
    const view = render(<Harness tick={0} />);
    const list = screen.getByTestId("messages-list");
    const metrics = attachScrollMetrics(list, {
      scrollHeight: 500,
      clientHeight: 200,
      scrollTop: 100,
    });

    fireEvent.scroll(list);

    metrics.setMetrics({ scrollHeight: 650 });
    view.rerender(<Harness tick={1} />);

    expect(metrics.readScrollTop()).toBe(100);
  });

  it("resumes auto-follow after the user scrolls back to the bottom", () => {
    const view = render(<Harness tick={0} />);
    const list = screen.getByTestId("messages-list");
    const metrics = attachScrollMetrics(list, {
      scrollHeight: 500,
      clientHeight: 200,
      scrollTop: 100,
    });

    fireEvent.scroll(list);

    metrics.setMetrics({ scrollHeight: 650 });
    view.rerender(<Harness tick={1} />);
    expect(metrics.readScrollTop()).toBe(100);

    metrics.setMetrics({ scrollTop: 450 });
    fireEvent.scroll(list);

    metrics.setMetrics({ scrollHeight: 780 });
    view.rerender(<Harness tick={2} />);

    expect(metrics.readScrollTop()).toBe(780);
  });

  it("keeps sticking to the bottom when DOM content grows after the watched value stops changing", async () => {
    const view = render(<Harness tick={1} extraContent={false} />);
    const list = screen.getByTestId("messages-list");
    const metrics = attachScrollMetrics(list, {
      scrollHeight: 500,
      clientHeight: 200,
      scrollTop: 300,
    });

    fireEvent.scroll(list);

    metrics.setMetrics({ scrollHeight: 650 });
    view.rerender(<Harness tick={1} extraContent={true} />);

    await waitFor(() => {
      expect(metrics.readScrollTop()).toBe(650);
    });
  });
});
