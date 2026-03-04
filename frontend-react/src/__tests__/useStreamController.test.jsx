import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useStreamController } from "../features/chat/useStreamController";

const streamChat = vi.fn();

vi.mock("../shared/api/chatApiClient", () => ({
  streamChat: (...args) => streamChat(...args),
}));

function ControllerHarness({ captureRef }) {
  const controller = useStreamController();
  captureRef.current = controller;
  return null;
}

describe("useStreamController", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    streamChat.mockReset();
  });

  it("awaits onAborted callback before resolving startStream", async () => {
    streamChat.mockImplementation(async (_payload, _handlers, options = {}) => {
      await new Promise((_, reject) => {
        const signal = options.signal;
        const abortError = () => signal?.reason ?? new DOMException("Aborted", "AbortError");
        if (signal?.aborted) {
          reject(abortError());
          return;
        }
        signal?.addEventListener("abort", () => reject(abortError()), { once: true });
      });
    });

    const captureRef = { current: null };
    render(<ControllerHarness captureRef={captureRef} />);

    const order = [];
    const startPromise = captureRef.current.startStream({
      payload: { message: "x" },
      onEvent: () => {},
      onDone: () => {},
      onTransportError: () => {},
      onAborted: async () => {
        order.push("aborted-start");
        await Promise.resolve();
        order.push("aborted-end");
      },
    });

    captureRef.current.abortStream();
    await startPromise;

    expect(order).toEqual(["aborted-start", "aborted-end"]);
  });

  it("awaits onTransportError callback before resolving startStream", async () => {
    streamChat.mockRejectedValueOnce(new Error("400 upstream failed"));

    const captureRef = { current: null };
    render(<ControllerHarness captureRef={captureRef} />);

    const order = [];
    await captureRef.current.startStream({
      payload: { message: "x" },
      onEvent: () => {},
      onDone: () => {},
      onAborted: () => {},
      onTransportError: async (message) => {
        order.push("error-start");
        await Promise.resolve();
        order.push(message);
      },
    });

    expect(order).toEqual(["error-start", "400 upstream failed"]);
  });
});
