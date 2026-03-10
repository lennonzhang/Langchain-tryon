import { render, screen, within } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import ModelSelect from "../components/ModelSelect";

const MODELS = [
  "moonshotai/kimi-k2.5",
  "qwen/qwen3.5-397b-a17b",
];

function StatefulHarness({
  models = MODELS,
  initialValue = MODELS[0],
  initialWebSearch = false,
  initialThinkingMode = false,
  supportsThinking = true,
  disabled = false,
  onChange = vi.fn(),
  onWebSearchChange = vi.fn(),
  onThinkingModeChange = vi.fn(),
}) {
  const [value, setValue] = useState(initialValue);
  const [webSearch, setWebSearch] = useState(initialWebSearch);
  const [thinkingMode, setThinkingMode] = useState(initialThinkingMode);

  return (
    <ModelSelect
      models={models}
      value={value}
      disabled={disabled}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
      webSearch={webSearch}
      onWebSearchChange={(next) => {
        setWebSearch(next);
        onWebSearchChange(next);
      }}
      supportsThinking={supportsThinking}
      thinkingMode={thinkingMode}
      onThinkingModeChange={(next) => {
        setThinkingMode(next);
        onThinkingModeChange(next);
      }}
    />
  );
}

describe("ModelSelect", () => {
  it("opens the menu, shows model options and embedded toggles, and allows model switching", async () => {
    const onChange = vi.fn();

    render(<StatefulHarness onChange={onChange} />);

    const trigger = screen.getByRole("button", { name: /kimi-k2\.5/i });
    await userEvent.click(trigger);

    expect(screen.getByRole("listbox")).toBeInTheDocument();
    expect(screen.getByText("qwen3.5-397b-a17b")).toBeInTheDocument();
    expect(screen.getByLabelText("Web Search")).toBeInTheDocument();
    expect(screen.getByLabelText("Thinking Mode")).toBeInTheDocument();

    await userEvent.click(screen.getByText("qwen3.5-397b-a17b"));

    expect(onChange).toHaveBeenCalledWith("qwen/qwen3.5-397b-a17b");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("button", { name: /qwen3\.5-397b-a17b/i })).toBeInTheDocument();
  });

  it("reflects enabled search and thinking state in trigger tags", async () => {
    render(<StatefulHarness />);

    const trigger = screen.getByRole("button", { name: /kimi-k2\.5/i });
    await userEvent.click(trigger);

    await userEvent.click(screen.getByLabelText("Web Search"));
    await userEvent.click(screen.getByLabelText("Thinking Mode"));

    expect(within(trigger).getByText("Search")).toBeInTheDocument();
    expect(within(trigger).getByText("Thinking")).toBeInTheDocument();
  });

  it("hides the thinking toggle when the active model does not support it", async () => {
    render(<StatefulHarness supportsThinking={false} />);

    await userEvent.click(screen.getByRole("button", { name: /kimi-k2\.5/i }));

    expect(screen.getByLabelText("Web Search")).toBeInTheDocument();
    expect(screen.queryByLabelText("Thinking Mode")).toBeNull();
  });

  it("does not open or emit changes when disabled", async () => {
    const onChange = vi.fn();
    const onWebSearchChange = vi.fn();
    const onThinkingModeChange = vi.fn();

    render(
      <StatefulHarness
        disabled={true}
        onChange={onChange}
        onWebSearchChange={onWebSearchChange}
        onThinkingModeChange={onThinkingModeChange}
      />
    );

    const trigger = screen.getByRole("button", { name: /kimi-k2\.5/i });
    expect(trigger).toBeDisabled();

    await userEvent.click(trigger);

    expect(screen.queryByRole("listbox")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
    expect(onWebSearchChange).not.toHaveBeenCalled();
    expect(onThinkingModeChange).not.toHaveBeenCalled();
  });

  it("closes the menu when clicking outside or pressing Escape", async () => {
    render(<StatefulHarness />);

    const trigger = screen.getByRole("button", { name: /kimi-k2\.5/i });
    await userEvent.click(trigger);
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("listbox")).toBeNull();

    await userEvent.click(trigger);
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("supports ArrowDown/ArrowUp keyboard navigation", async () => {
    render(<StatefulHarness />);

    const trigger = screen.getByRole("button", { name: /kimi-k2\.5/i });
    await userEvent.click(trigger);

    const options = screen.getAllByRole("option");
    expect(options[0]).toHaveFocus();

    fireEvent.keyDown(options[0], { key: "ArrowDown" });
    expect(options[1]).toHaveFocus();

    fireEvent.keyDown(options[1], { key: "ArrowUp" });
    expect(options[0]).toHaveFocus();
  });

  it("selects an option with Enter and returns focus to trigger", async () => {
    const onChange = vi.fn();
    render(<StatefulHarness onChange={onChange} />);

    const trigger = screen.getByRole("button", { name: /kimi-k2\.5/i });
    await userEvent.click(trigger);

    const options = screen.getAllByRole("option");
    fireEvent.keyDown(options[0], { key: "ArrowDown" });
    fireEvent.keyDown(options[1], { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith("qwen/qwen3.5-397b-a17b");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("button", { name: /qwen3\.5-397b-a17b/i })).toHaveFocus();
  });

  it("selects an option with Space key", async () => {
    const onChange = vi.fn();
    render(<StatefulHarness onChange={onChange} />);

    const trigger = screen.getByRole("button", { name: /kimi-k2\.5/i });
    await userEvent.click(trigger);

    const options = screen.getAllByRole("option");
    fireEvent.keyDown(options[0], { key: " " });

    expect(onChange).toHaveBeenCalledWith("moonshotai/kimi-k2.5");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("returns focus to trigger on Escape", async () => {
    render(<StatefulHarness />);

    const trigger = screen.getByRole("button", { name: /kimi-k2\.5/i });
    await userEvent.click(trigger);
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("shows a disabled empty state when no models are available", async () => {
    const onChange = vi.fn();
    render(<StatefulHarness models={[]} initialValue="" onChange={onChange} />);

    const trigger = screen.getByRole("button", { name: /no models available/i });
    expect(trigger).toBeDisabled();

    await userEvent.click(trigger);
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.keyDown(trigger, { key: "Enter" });

    expect(screen.queryByRole("listbox")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });
});
