import { streamChat } from "../../shared/api/chatApiClient";

export function useStreamController() {
  async function startStream({ payload, onEvent, onDone, onTransportError }) {
    try {
      await streamChat(payload, {
        onEvent,
        onDone,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Request failed";
      onTransportError?.(message);
    }
  }

  return { startStream };
}
