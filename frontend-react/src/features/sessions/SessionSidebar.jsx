import { useState, useRef, useEffect } from "react";
import SessionList from "./SessionList";

const FILTER_DEBOUNCE_MS = 200;

export default function SessionSidebar({
  sessions,
  activeSessionId,
  runningSessionId,
  filter,
  isOpen,
  onToggle,
  onFilterChange,
  onCreateNew,
  onSelect,
  onDelete,
}) {
  const [localFilter, setLocalFilter] = useState(filter);
  const timerRef = useRef(null);

  // Sync external filter changes (e.g. reset) to local state
  useEffect(() => {
    setLocalFilter(filter);
  }, [filter]);

  // Cleanup debounce timer on unmount
  useEffect(() => () => clearTimeout(timerRef.current), []);

  function handleFilterInput(value) {
    setLocalFilter(value);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => onFilterChange(value), FILTER_DEBOUNCE_MS);
  }

  return (
    <aside className={`session-sidebar ${isOpen ? "is-open" : ""}`}>
      {isOpen && (
        <div
          className="sidebar-backdrop"
          onClick={onToggle}
          aria-hidden="true"
        />
      )}
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
          value={localFilter}
          onChange={(event) => handleFilterInput(event.target.value)}
        />
      </div>
      <SessionList
        sessions={sessions}
        activeSessionId={activeSessionId}
        runningSessionId={runningSessionId}
        filter={localFilter}
        onSelect={onSelect}
        onDelete={onDelete}
      />
    </aside>
  );
}
