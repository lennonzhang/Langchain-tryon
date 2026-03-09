import { memo, useMemo } from "react";

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

function SessionList({
  sessions,
  activeSessionId,
  runningSessionId = null,
  filter,
  onSelect,
  onDelete,
  onCreateNew,
}) {
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

  return (
    <>
      <ul className="session-list" data-testid="session-list">
        {typeof onCreateNew === "function" && (
          <li className="session-row session-row-entry">
            <button
              type="button"
              className="session-item session-item-new"
              onClick={onCreateNew}
              aria-label="New chat"
            >
              <span className="session-item-new-icon" aria-hidden="true">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              </span>
              <span className="session-item-new-copy">
                <span className="session-item-new-title">New chat</span>
                <span className="session-item-new-subtitle">Start a fresh draft above your saved sessions.</span>
              </span>
            </button>
          </li>
        )}
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
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </li>
          );
        })}
      </ul>
      {visible.length === 0 && (
        <div className="session-empty">
          {normalizedFilter ? "No matches for this search." : "No conversation yet."}
        </div>
      )}
    </>
  );
}

export default memo(SessionList);
