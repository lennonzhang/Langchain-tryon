import React, { Suspense } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("bootstrap", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unmock("../App");
    vi.unmock("../utils/markdown");
    vi.unmock("react-dom/client");
  });

  it("mountApp renders into the root and schedules markdown warmup", async () => {
    const renderMock = vi.fn();
    const createRootMock = vi.fn(() => ({ render: renderMock }));
    const warmupMock = vi.fn();

    vi.doMock("../App", () => ({
      default: () => <div>Mock App</div>,
    }));
    vi.doMock("../utils/markdown", async () => {
      const actual = await vi.importActual("../utils/markdown");
      return {
        ...actual,
        scheduleMarkdownWarmup: warmupMock,
      };
    });
    vi.doMock("react-dom/client", () => ({
      createRoot: createRootMock,
    }));

    const { mountApp } = await import("../bootstrap.jsx");
    const root = document.createElement("div");

    mountApp(root);

    expect(createRootMock).toHaveBeenCalledWith(root);
    expect(renderMock).toHaveBeenCalledTimes(1);
    expect(warmupMock).toHaveBeenCalledTimes(1);
  });

  it("lazyOptional renders the loaded component", async () => {
    const { lazyOptional } = await import("../bootstrap.jsx");
    const LoadedComponent = lazyOptional(
      () => Promise.resolve({ DemoWidget: () => <div>Loaded widget</div> }),
      "DemoWidget",
    );

    render(
      <Suspense fallback={<div>Loading</div>}>
        <LoadedComponent />
      </Suspense>,
    );

    expect(await screen.findByText("Loaded widget")).toBeInTheDocument();
  });

  it("lazyOptional falls back to Noop when the optional chunk fails", async () => {
    const { lazyOptional } = await import("../bootstrap.jsx");
    const OptionalComponent = lazyOptional(() => Promise.reject(new Error("chunk failed")), "Analytics");
    const { container } = render(
      <Suspense fallback={<div>Loading</div>}>
        <OptionalComponent />
      </Suspense>,
    );

    await waitFor(() => {
      expect(screen.queryByText("Loading")).toBeNull();
    });
    expect(container).toBeEmptyDOMElement();
  });
});
