import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import SessionSidebar from "../features/sessions/SessionSidebar";

const sessions = [
  {
    id: "s1",
    title: "Session One",
    updatedAt: "2026-01-01T00:00:00.000Z",
    lastMessagePreview: "Preview",
  },
];

function mockMatchMedia(matches) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches,
      media: "(max-width: 600px)",
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe("SessionSidebar", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("auto closes on mobile after selecting a session or creating new chat", async () => {
    mockMatchMedia(true);
    const onSelect = vi.fn();
    const onCreateNew = vi.fn();
    const onClose = vi.fn();

    render(
      <SessionSidebar
        sessions={sessions}
        activeSessionId="s1"
        runningSessionId={null}
        filter=""
        isOpen={true}
        onToggle={() => {}}
        onClose={onClose}
        onFilterChange={() => {}}
        onCreateNew={onCreateNew}
        onSelect={onSelect}
        onDelete={() => {}}
      />,
    );

    await userEvent.click(screen.getByText("Session One"));
    expect(onSelect).toHaveBeenCalledWith("s1");
    expect(onClose).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByText("+ New Chat"));
    expect(onCreateNew).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("does not auto close on desktop when selecting or creating", async () => {
    mockMatchMedia(false);
    const onSelect = vi.fn();
    const onCreateNew = vi.fn();
    const onClose = vi.fn();

    render(
      <SessionSidebar
        sessions={sessions}
        activeSessionId="s1"
        runningSessionId={null}
        filter=""
        isOpen={true}
        onToggle={() => {}}
        onClose={onClose}
        onFilterChange={() => {}}
        onCreateNew={onCreateNew}
        onSelect={onSelect}
        onDelete={() => {}}
      />,
    );

    await userEvent.click(screen.getByText("Session One"));
    await userEvent.click(screen.getByText("+ New Chat"));

    expect(onSelect).toHaveBeenCalledWith("s1");
    expect(onCreateNew).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("clicking backdrop closes the sidebar", async () => {
    const onClose = vi.fn();

    render(
      <SessionSidebar
        sessions={sessions}
        activeSessionId="s1"
        runningSessionId={null}
        filter=""
        isOpen={true}
        onToggle={() => {}}
        onClose={onClose}
        onFilterChange={() => {}}
        onCreateNew={() => {}}
        onSelect={() => {}}
        onDelete={() => {}}
      />,
    );

    const backdrop = document.querySelector(".sidebar-backdrop");
    expect(backdrop).toBeTruthy();
    await userEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
