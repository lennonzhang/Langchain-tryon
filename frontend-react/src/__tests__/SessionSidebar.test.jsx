import { cleanup, render, screen } from "@testing-library/react";
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

function renderSidebar(props = {}) {
  return render(
    <SessionSidebar
      sessions={sessions}
      activeSessionId="s1"
      runningSessionId={null}
      filter=""
      isOpen={true}
      onToggle={() => {}}
      onClose={() => {}}
      onFilterChange={() => {}}
      onCreateNew={() => {}}
      onSelect={() => {}}
      onDelete={() => {}}
      {...props}
    />,
  );
}

describe("SessionSidebar", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("auto closes in overlay mode after selecting a session or creating new chat", async () => {
    const onSelect = vi.fn();
    const onCreateNew = vi.fn();
    const onClose = vi.fn();

    renderSidebar({ overlayMode: true, onClose, onCreateNew, onSelect });

    const sessionButton = document.querySelector(".session-row:not(.session-row-entry) .session-item");
    expect(sessionButton).toBeTruthy();
    await userEvent.click(sessionButton);
    expect(onSelect).toHaveBeenCalledWith("s1");
    expect(onClose).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByLabelText("New chat"));
    expect(onCreateNew).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("does not auto close on desktop when selecting or creating", async () => {
    const onSelect = vi.fn();
    const onCreateNew = vi.fn();
    const onClose = vi.fn();

    renderSidebar({ overlayMode: false, onClose, onCreateNew, onSelect });

    const sessionButton = document.querySelector(".session-row:not(.session-row-entry) .session-item");
    expect(sessionButton).toBeTruthy();
    await userEvent.click(sessionButton);
    await userEvent.click(screen.getByLabelText("New chat"));

    expect(onSelect).toHaveBeenCalledWith("s1");
    expect(onCreateNew).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("clicking backdrop closes the sidebar", async () => {
    const onClose = vi.fn();

    renderSidebar({ overlayMode: true, onClose });

    const backdrop = document.querySelector(".sidebar-backdrop");
    expect(backdrop).toBeTruthy();
    await userEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not render a backdrop outside overlay mode", () => {
    renderSidebar({ overlayMode: false });
    expect(document.querySelector(".sidebar-backdrop")).toBeNull();
  });

  it("close button closes the sidebar", async () => {
    const onClose = vi.fn();

    renderSidebar({ overlayMode: true, onClose });

    await userEvent.click(screen.getByRole("button", { name: "Close sessions panel" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
