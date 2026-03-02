import SessionList from "./SessionList";

export default function SessionSidebar({
  sessions,
  activeSessionId,
  filter,
  isOpen,
  onToggle,
  onFilterChange,
  onCreateNew,
  onSelect,
  onDelete,
}) {
  return (
    <aside className={`session-sidebar ${isOpen ? "is-open" : ""}`}>
      <div className="session-toolbar">
        <button type="button" className="session-toggle" onClick={onToggle} aria-label="Toggle sessions">
          Sessions
        </button>
        <button type="button" className="session-new" onClick={onCreateNew}>
          + New Chat
        </button>
      </div>
      <div className="session-filter-wrap">
        <input
          className="session-filter"
          placeholder="Filter history"
          value={filter}
          onChange={(event) => onFilterChange(event.target.value)}
        />
      </div>
      <SessionList
        sessions={sessions}
        activeSessionId={activeSessionId}
        filter={filter}
        onSelect={onSelect}
        onDelete={onDelete}
      />
    </aside>
  );
}
