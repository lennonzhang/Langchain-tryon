import { useRef, useCallback } from "react";
import { streamChat } from "../../shared/api/chatApiClient";

const MAX_RETRIES = 1;
const RETRY_DELAY_MS = 2000;

function isRetryable(error) {
  if (error.name === "AbortError") return false;
  // Retry on network errors (TypeError from fetch) or 5xx status codes
  if (error instanceof TypeError) return true;
  if (/^5\d{2}\b/.test(error.message)) return true;
  if (/network|fetch|ECONNRESET/i.test(error.message)) return true;
  return false;
}

function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    const id = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(id);
        reject(signal.reason ?? new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

export function useStreamController() {
  const controllerRef = useRef(null);

  const abortStream = useCallback(() => {
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
    }
  }, []);

  const startStream = useCallback(async ({ payload, onEvent, onDone, onTransportError, onAborted }) => {
    if (controllerRef.current) {
      await Promise.resolve(onTransportError?.("Another stream is already running"));
      return;
    }

    const controller = new AbortController();
    controllerRef.current = controller;

    let receivedToken = false;
    let attempt = 0;

    const wrappedOnEvent = (event) => {
      if (event.type === "token" || event.type === "reasoning") {
        receivedToken = true;
      }
      return onEvent(event);
    };

    try {
      while (attempt <= MAX_RETRIES) {
        try {
          await streamChat(payload, { onEvent: wrappedOnEvent, onDone }, { signal: controller.signal });
          break; // success
        } catch (error) {
          if (error.name === "AbortError") {
            await Promise.resolve(onAborted?.());
            return;
          }

          const canRetry = !receivedToken && isRetryable(error) && attempt < MAX_RETRIES;
          if (canRetry) {
            attempt++;
            await wait(RETRY_DELAY_MS, controller.signal);
            continue;
          }

          const message = error instanceof Error ? error.message : "Request failed";
          await Promise.resolve(onTransportError?.(message));
          return;
        }
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    }
  }, []);

  return { startStream, abortStream };
}
