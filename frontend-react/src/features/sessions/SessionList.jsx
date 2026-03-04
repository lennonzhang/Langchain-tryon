function formatTime(isoTime) {
  if (!isoTime) return "";
  const date = new Date(isoTime);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

export default function SessionList({ sessions, activeSessionId, runningSessionId = null, filter, onSelect, onDelete }) {
  const normalizedFilter = (filter || "").trim().toLowerCase();
  const visible = normalizedFilter
    ? sessions.filter((session) => {
        return (
          session.title.toLowerCase().includes(normalizedFilter) ||
          (session.lastMessagePreview || "").toLowerCase().includes(normalizedFilter)
        );
      })
    : sessions;

  if (visible.length === 0) {
    return <div className="session-empty">No conversation yet.</div>;
  }

  return (
    <ul className="session-list" data-testid="session-list">
      {visible.map((session) => (
        <li key={session.id}>
          {session.id === runningSessionId && (
            <span className="session-running-badge" aria-label={`Running ${session.title}`}>
              Running
            </span>
          )}
          <button
            type="button"
            className={`session-item ${activeSessionId === session.id ? "is-active" : ""}`}
            onClick={() => onSelect(session.id)}
          >
            <span className="session-title">{session.title}</span>
            <span className="session-time">{formatTime(session.updatedAt)}</span>
            <span className="session-preview">{session.lastMessagePreview || "No assistant response yet."}</span>
          </button>
          <button
            type="button"
            className="session-delete"
            aria-label={`Delete ${session.title}`}
            disabled={session.id === runningSessionId}
            onClick={() => onDelete(session.id)}
          >
            Delete
          </button>
        </li>
      ))}
    </ul>
  );
}
