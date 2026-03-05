import { useState, useRef, useEffect } from "react";
import SessionList from "./SessionList";

const FILTER_DEBOUNCE_MS = 200;
const MOBILE_MEDIA_QUERY = "(max-width: 600px)";

function isMobileViewport() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

export default function SessionSidebar({
  sessions,
  activeSessionId,
  runningSessionId,
  filter,
  isOpen,
  onToggle,
  onClose,
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

  function handleClearFilter() {
    clearTimeout(timerRef.current);
    setLocalFilter("");
    onFilterChange("");
  }

  function closeOnMobile() {
    if (!isMobileViewport()) return;
    onClose?.();
  }

  function handleCreateNew() {
    onCreateNew();
    closeOnMobile();
  }

  function handleSelect(sessionId) {
    onSelect(sessionId);
    closeOnMobile();
  }

  return (
    <>
      {isOpen && (
        <div
          className="sidebar-backdrop"
          onClick={onClose || onToggle}
          aria-hidden="true"
        />
      )}
      <aside id="session-sidebar" className={`session-sidebar ${isOpen ? "is-open" : ""}`}>
        <div className="session-header">
          <div className="session-header-text">
            <div className="session-kicker">Workspace</div>
            <h2>Sessions</h2>
            <p className="session-count">
              {sessions.length} conversation{sessions.length === 1 ? "" : "s"}
            </p>
          </div>
          <button type="button" className="session-new session-new-primary" onClick={handleCreateNew}>
            + New Chat
          </button>
        </div>
        <div className="session-toolbar">
          <button type="button" className="session-toggle" onClick={onToggle} aria-label="Toggle sessions">
            Toggle
          </button>
          <div className="session-filter-wrap">
            <span className="session-filter-icon" aria-hidden="true">
              Search
            </span>
            <input
              className="session-filter"
              placeholder="Search sessions"
              value={localFilter}
              onChange={(event) => handleFilterInput(event.target.value)}
            />
            {localFilter && (
              <button
                type="button"
                className="session-filter-clear"
                aria-label="Clear filter"
                onClick={handleClearFilter}
              >
                Clear
              </button>
            )}
          </div>
        </div>
        <div className="session-list-hint">Recent activity first</div>
        <SessionList
          sessions={sessions}
          activeSessionId={activeSessionId}
          runningSessionId={runningSessionId}
          filter={localFilter}
          onSelect={handleSelect}
          onDelete={onDelete}
        />
      </aside>
    </>
  );
}
