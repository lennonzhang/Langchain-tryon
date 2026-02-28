import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App, { shortModelName } from "../App";
import { parseEventStream } from "../stream";

vi.mock("../stream", () => ({
  parseEventStream: vi.fn(),
}));

const CAPABILITIES_RESPONSE = {
  version: 1,
  default: "moonshotai/kimi-k2.5",
  models: [
    { id: "moonshotai/kimi-k2.5", label: "Kimi K2.5", capabilities: { thinking: true, media: true, agent: false }, context_window: 131072 },
    { id: "qwen/qwen3.5-397b-a17b", label: "Qwen 3.5", capabilities: { thinking: true, media: false, agent: true }, context_window: 128000 },
    { id: "z-ai/glm5", label: "GLM 5", capabilities: { thinking: true, media: false, agent: true }, context_window: 128000 },
  ],
};

function mockFetchOk(capabilities = CAPABILITIES_RESPONSE) {
  global.fetch = vi.fn().mockImplementation((url) => {
    if (typeof url === "string" && url.includes("/api/capabilities")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(capabilities),
      });
    }
    return Promise.resolve({
      ok: true,
      body: { getReader: () => ({}) },
    });
  });
}

function deferred() {
  let resolve;
  const promise = new Promise((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe("App behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchOk();
    class MockFileReader {
      readAsDataURL(file) {
        this.result = `data:${file.type};base64,ZmFrZQ==`;
        setTimeout(() => this.onload?.(), 0);
      }
    }
    global.FileReader = MockFileReader;
    global.URL.createObjectURL = vi.fn(() => "blob:mock");
    global.URL.revokeObjectURL = vi.fn();
  });

  it("exports shortModelName helper", () => {
    expect(shortModelName("qwen/qwen3.5-397b-a17b")).toBe("qwen3.5-397b-a17b");
  });

  it("uses backend default model from capabilities response", async () => {
    mockFetchOk({
      ...CAPABILITIES_RESPONSE,
      default: "z-ai/glm5",
    });

    const { container } = render(<App />);
    await waitFor(() => {
      expect(container.querySelector(".model-trigger-label")?.textContent).toBe("glm5");
    });
  });

  it("renders search/reasoning/usage sections from streaming events", async () => {
    parseEventStream.mockImplementation(async (_reader, onEvent) => {
      onEvent({ type: "search_start", query: "qwen news" });
      onEvent({ type: "search_done", results: [{ title: "R1", url: "https://a.com", snippet: "s" }] });
      onEvent({
        type: "context_usage",
        usage: {
          phase: "single",
          used_estimated_tokens: 100,
          window_total_tokens: 1000,
          usage_ratio: 0.1,
          model: "moonshotai/kimi-k2.5",
        },
      });
      onEvent({ type: "reasoning", content: "step-1" });
      onEvent({ type: "token", content: "final answer" });
      onEvent({ type: "done" });
    });

    render(<App />);

    const input = screen.getByRole("textbox");
    await userEvent.type(input, "hello");
    fireEvent.submit(document.querySelector("form.composer"));

    expect(await screen.findByTestId("search-panel")).toBeInTheDocument();
    expect(await screen.findByTestId("usage-panel")).toBeInTheDocument();
    expect(await screen.findByTestId("reasoning-panel")).toBeInTheDocument();
    expect(screen.getByText("final answer")).toBeInTheDocument();
    expect(screen.getByText(/\[single\] 100\/1000 tokens/)).toBeInTheDocument();
  });

  it("shows stream error when SSE emits error event", async () => {
    parseEventStream.mockImplementation(async (_reader, onEvent) => {
      onEvent({ type: "error", error: "boom" });
    });

    render(<App />);
    await userEvent.type(screen.getByRole("textbox"), "hello");
    fireEvent.submit(document.querySelector("form.composer"));

    expect(await screen.findByText("Error: boom")).toBeInTheDocument();
    expect(screen.queryByText("(empty response)")).not.toBeInTheDocument();
  });

  it("keeps error UI when stream sends error followed by done", async () => {
    parseEventStream.mockImplementation(async (_reader, onEvent) => {
      try {
        onEvent({ type: "error", error: "boom-after-done" });
      } catch {
        onEvent({ type: "done" });
        throw new Error("boom-after-done");
      }
    });

    render(<App />);
    await userEvent.type(screen.getByRole("textbox"), "hello");
    fireEvent.submit(document.querySelector("form.composer"));

    expect(await screen.findByText("Error: boom-after-done")).toBeInTheDocument();
    expect(screen.queryByText("(empty response)")).not.toBeInTheDocument();
  });

  it("clears media attachments when switching from kimi to qwen", async () => {
    parseEventStream.mockImplementation(async (_reader, onEvent) => {
      onEvent({ type: "token", content: "ok" });
      onEvent({ type: "done" });
    });

    const { container } = render(<App />);
    const fileInput = container.querySelector('input[type="file"]');
    const file = new File(["x"], "pic.png", { type: "image/png" });
    await userEvent.upload(fileInput, file);

    await waitFor(() => {
      expect(container.querySelectorAll(".attach-thumb").length).toBe(1);
    });
    expect(screen.getByTestId("attach-strip")).toBeInTheDocument();

    await userEvent.click(container.querySelector(".model-trigger"));
    await userEvent.click(screen.getByText("qwen/qwen3.5-397b-a17b"));

    await waitFor(() => {
      expect(screen.queryByTestId("attach-strip")).not.toBeInTheDocument();
    });
  });

  it("preserves user model choice when capabilities resolves later", async () => {
    const capsReq = deferred();
    global.fetch = vi.fn().mockImplementation((url) => {
      if (typeof url === "string" && url.includes("/api/capabilities")) {
        return capsReq.promise;
      }
      return Promise.resolve({
        ok: true,
        body: { getReader: () => ({}) },
      });
    });

    const { container } = render(<App />);
    await userEvent.click(container.querySelector(".model-trigger"));
    await userEvent.click(screen.getByText("z-ai/glm5"));
    await waitFor(() => {
      expect(container.querySelector(".model-trigger-label")?.textContent).toBe("glm5");
    });

    capsReq.resolve({
      ok: true,
      json: () => Promise.resolve(CAPABILITIES_RESPONSE),
    });

    await waitFor(() => {
      expect(container.querySelector(".model-trigger-label")?.textContent).toBe("glm5");
    });
  });

  it("falls back to valid model if selected model is not in capabilities", async () => {
    const capsReq = deferred();
    global.fetch = vi.fn().mockImplementation((url) => {
      if (typeof url === "string" && url.includes("/api/capabilities")) {
        return capsReq.promise;
      }
      return Promise.resolve({
        ok: true,
        body: { getReader: () => ({}) },
      });
    });

    const { container } = render(<App />);
    await userEvent.click(container.querySelector(".model-trigger"));
    await userEvent.click(screen.getByText("z-ai/glm5"));
    await waitFor(() => {
      expect(container.querySelector(".model-trigger-label")?.textContent).toBe("glm5");
    });

    capsReq.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          version: 1,
          default: "moonshotai/kimi-k2.5",
          models: [
            {
              id: "moonshotai/kimi-k2.5",
              label: "Kimi K2.5",
              capabilities: { thinking: true, media: true, agent: false },
              context_window: 131072,
            },
          ],
        }),
    });

    await waitFor(() => {
      expect(container.querySelector(".model-trigger-label")?.textContent).toBe("kimi-k2.5");
    });
  });
});
