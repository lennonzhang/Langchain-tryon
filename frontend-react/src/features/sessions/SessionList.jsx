import { useMemo } from "react";

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function parseValidDate(isoTime) {
  if (!isoTime) return null;
  const date = new Date(isoTime);
  return Number.isNaN(date.getTime()) ? null : date;
}

export default function SessionList({ sessions, activeSessionId, runningSessionId = null, filter, onSelect, onDelete }) {
  const normalizedFilter = (filter || "").trim().toLowerCase();
  const visible = useMemo(() => {
    if (!normalizedFilter) {
      return sessions;
    }
    return sessions.filter((session) => {
      return (
        session.title.toLowerCase().includes(normalizedFilter) ||
        (session.lastMessagePreview || "").toLowerCase().includes(normalizedFilter)
      );
    });
  }, [sessions, normalizedFilter]);

  if (visible.length === 0) {
    return (
      <div className="session-empty">
        {normalizedFilter ? "No matches for this search." : "No conversation yet."}
      </div>
    );
  }

  return (
    <ul className="session-list" data-testid="session-list">
      {visible.map((session) => {
        const isActive = activeSessionId === session.id;
        const isRunning = session.id === runningSessionId;
        const validDate = parseValidDate(session.updatedAt);
        const timeLabel = validDate ? dateTimeFormatter.format(validDate) : "";
        const timeTitle = validDate ? validDate.toLocaleString() : "";

        return (
          <li
            key={session.id}
            className={`session-row ${isActive ? "is-active" : ""} ${isRunning ? "is-running" : ""}`}
          >
            <button
              type="button"
              className={`session-item ${isActive ? "is-active" : ""}`}
              onClick={() => onSelect(session.id)}
            >
              <span className="session-item-top">
                <span className="session-title">{session.title}</span>
                <span className="session-time" title={timeTitle}>
                  {timeLabel}
                </span>
              </span>
              <span className="session-preview">{session.lastMessagePreview || "No assistant response yet."}</span>
              <span className="session-badges">
                {isActive && <span className="session-badge active">Active</span>}
                {isRunning && (
                  <span className="session-badge running" aria-label={`Running ${session.title}`}>
                    Running
                  </span>
                )}
              </span>
            </button>
            <button
              type="button"
              className="session-delete"
              aria-label={`Delete ${session.title}`}
              disabled={isRunning}
              onClick={() => onDelete(session.id)}
            >
              Delete
            </button>
          </li>
        );
      })}
    </ul>
  );
}
