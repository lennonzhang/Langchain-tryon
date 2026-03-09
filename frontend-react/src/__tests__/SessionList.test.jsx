import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import SessionList from "../features/sessions/SessionList";

const sessions = [
  {
    id: "s1",
    title: "First",
    updatedAt: "2026-01-01T00:00:00.000Z",
    lastMessagePreview: "hello",
  },
  {
    id: "s2",
    title: "Second",
    updatedAt: "2026-01-01T00:01:00.000Z",
    lastMessagePreview: "world",
  },
];

describe("SessionList", () => {
  it("renders and allows select/delete", async () => {
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    const onCreateNew = vi.fn();

    render(
      <SessionList
        sessions={sessions}
        activeSessionId="s1"
        filter=""
        onCreateNew={onCreateNew}
        onSelect={onSelect}
        onDelete={onDelete}
      />,
    );

    await userEvent.click(screen.getByLabelText("New chat"));
    expect(onCreateNew).toHaveBeenCalledTimes(1);

    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Second"));
    expect(onSelect).toHaveBeenCalledWith("s2");

    await userEvent.click(screen.getByLabelText("Delete First"));
    expect(onDelete).toHaveBeenCalledWith("s1");
  });

  it("shows empty state", () => {
    render(
      <SessionList
        sessions={[]}
        activeSessionId={null}
        filter=""
        onCreateNew={() => {}}
        onSelect={() => {}}
        onDelete={() => {}}
      />,
    );

    expect(screen.getByText("No conversation yet.")).toBeInTheDocument();
  });

  it("marks running session and disables its delete button", () => {
    const onDelete = vi.fn();

    render(
      <SessionList
        sessions={sessions}
        activeSessionId="s1"
        runningSessionId="s2"
        filter=""
        onCreateNew={() => {}}
        onSelect={() => {}}
        onDelete={onDelete}
      />,
    );

    expect(screen.getByLabelText("Running Second")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByLabelText("Delete Second")).toBeDisabled();
    expect(screen.getByLabelText("Delete First")).not.toBeDisabled();
  });

  it("does not render Invalid Date tooltip when updatedAt is invalid", () => {
    render(
      <SessionList
        sessions={[
          {
            id: "broken",
            title: "Broken Time",
            updatedAt: "not-a-date",
            lastMessagePreview: "preview",
          },
        ]}
        activeSessionId="broken"
        filter=""
        onCreateNew={() => {}}
        onSelect={() => {}}
        onDelete={() => {}}
      />,
    );

    const timeEl = document.querySelector(".session-time");
    expect(timeEl).toBeTruthy();
    expect(timeEl?.getAttribute("title")).toBe("");
  });

  it("keeps long title and preview in fixed text columns", () => {
    render(
      <SessionList
        sessions={[
          {
            id: "long",
            title: "A very very very very very long title for width stability",
            updatedAt: "2026-01-01T00:00:00.000Z",
            lastMessagePreview:
              "A long assistant preview used to ensure the item still renders under fixed text-column constraints.",
          },
        ]}
        activeSessionId="long"
        filter=""
        onCreateNew={() => {}}
        onSelect={() => {}}
        onDelete={() => {}}
      />,
    );

    const item = document.querySelector(".session-row:not(.session-row-entry) .session-item");
    const title = document.querySelector(".session-title");
    const preview = document.querySelector(".session-preview");
    expect(item?.querySelector(".session-item-top")).toBeTruthy();
    expect(title).toBeTruthy();
    expect(preview).toBeTruthy();
  });

  it("renders new chat entry before saved sessions", () => {
    render(
      <SessionList
        sessions={sessions}
        activeSessionId="s1"
        filter=""
        onCreateNew={() => {}}
        onSelect={() => {}}
        onDelete={() => {}}
      />,
    );

    const rows = screen.getByTestId("session-list").querySelectorAll(".session-row");
    expect(rows[0]?.classList.contains("session-row-entry")).toBe(true);
  });
});
