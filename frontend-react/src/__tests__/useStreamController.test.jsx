import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useStreamController } from "../features/chat/useStreamController";

const streamChat = vi.fn();
const cancelChat = vi.fn();

vi.mock("../shared/api/chatApiClient", () => ({
  streamChat: (...args) => streamChat(...args),
  cancelChat: (...args) => cancelChat(...args),
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
    cancelChat.mockResolvedValue({ cancelled: true });
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
      payload: { message: "x", request_id: "req-1" },
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

    expect(cancelChat).toHaveBeenCalledWith("req-1");
    expect(order).toEqual(["aborted-start", "aborted-end"]);
  });

  it("waits for cancel confirmation before aborting local stream", async () => {
    let abortObserved = false;
    let resolveCancel;
    cancelChat.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCancel = resolve;
        }),
    );
    streamChat.mockImplementation(async (_payload, _handlers, options = {}) => {
      await new Promise((_, reject) => {
        const signal = options.signal;
        const abortError = () => signal?.reason ?? new DOMException("Aborted", "AbortError");
        signal?.addEventListener(
          "abort",
          () => {
            abortObserved = true;
            reject(abortError());
          },
          { once: true },
        );
      });
    });

    const captureRef = { current: null };
    render(<ControllerHarness captureRef={captureRef} />);

    const startPromise = captureRef.current.startStream({
      payload: { message: "x", request_id: "req-2" },
      onEvent: () => {},
      onDone: () => {},
      onTransportError: () => {},
      onAborted: () => {},
    });

    const abortPromise = captureRef.current.abortStream();
    await Promise.resolve();

    expect(cancelChat).toHaveBeenCalledWith("req-2");
    expect(abortObserved).toBe(false);

    resolveCancel({ cancelled: true });
    await abortPromise;
    await startPromise;

    expect(abortObserved).toBe(true);
  });

  it("still aborts locally when cancel request fails", async () => {
    let abortObserved = false;
    cancelChat.mockRejectedValueOnce(new Error("cancel failed"));
    streamChat.mockImplementation(async (_payload, _handlers, options = {}) => {
      await new Promise((_, reject) => {
        const signal = options.signal;
        const abortError = () => signal?.reason ?? new DOMException("Aborted", "AbortError");
        signal?.addEventListener(
          "abort",
          () => {
            abortObserved = true;
            reject(abortError());
          },
          { once: true },
        );
      });
    });

    const captureRef = { current: null };
    render(<ControllerHarness captureRef={captureRef} />);

    const startPromise = captureRef.current.startStream({
      payload: { message: "x", request_id: "req-3" },
      onEvent: () => {},
      onDone: () => {},
      onTransportError: () => {},
      onAborted: () => {},
    });

    await captureRef.current.abortStream();
    await startPromise;

    expect(cancelChat).toHaveBeenCalledWith("req-3");
    expect(abortObserved).toBe(true);
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
