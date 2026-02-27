import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App, {
  modelSupportsMediaInput,
  modelSupportsThinking,
  shortModelName,
} from "../App";
import { parseEventStream } from "../stream";

vi.mock("../stream", () => ({
  parseEventStream: vi.fn(),
}));

function mockFetchOk() {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    body: { getReader: () => ({}) },
  });
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

  it("exports model capability helpers", () => {
    expect(modelSupportsThinking("moonshotai/kimi-k2.5")).toBe(true);
    expect(modelSupportsThinking("qwen/qwen3.5-397b-a17b")).toBe(true);
    expect(modelSupportsThinking("z-ai/glm5")).toBe(true);
    expect(modelSupportsMediaInput("moonshotai/kimi-k2.5")).toBe(true);
    expect(modelSupportsMediaInput("qwen/qwen3.5-397b-a17b")).toBe(false);
    expect(shortModelName("qwen/qwen3.5-397b-a17b")).toBe("qwen3.5-397b-a17b");
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
});
