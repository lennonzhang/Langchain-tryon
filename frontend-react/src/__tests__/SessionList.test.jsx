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

    render(
      <SessionList
        sessions={sessions}
        activeSessionId="s1"
        filter=""
        onSelect={onSelect}
        onDelete={onDelete}
      />,
    );

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
        onSelect={() => {}}
        onDelete={() => {}}
      />,
    );

    expect(screen.getByText("No conversation yet.")).toBeInTheDocument();
  });
});
