import { memo, useState, useRef, useEffect } from "react";
import SessionList from "./SessionList";

const FILTER_DEBOUNCE_MS = 200;

function SessionSidebar({
  sidebarRef,
  sessions,
  activeSessionId,
  runningSessionId,
  filter,
  isOpen,
  overlayMode = false,
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

  function closeOnOverlay() {
    if (!overlayMode) return;
    onClose?.();
  }

  function handleCreateNew() {
    onCreateNew();
    closeOnOverlay();
  }

  function handleSelect(sessionId) {
    onSelect(sessionId);
    closeOnOverlay();
  }

  return (
    <>
      {overlayMode && isOpen && (
        <div
          className="sidebar-backdrop"
          onClick={onClose || onToggle}
          aria-hidden="true"
        />
      )}
      <aside
        ref={sidebarRef}
        id="session-sidebar"
        className={`session-sidebar ${isOpen ? "is-open" : ""}`}
      >
        <div className="session-header">
          <div className="session-header-text">
            <h2>Sessions</h2>
            <p className="session-count">
              {sessions.length} conversation{sessions.length === 1 ? "" : "s"}
            </p>
          </div>
          <button
            type="button"
            className="session-close"
            aria-label="Close sessions panel"
            onClick={onClose || onToggle}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div className="session-toolbar">
          <div className="session-filter-wrap">
            <svg className="session-filter-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input
              className="session-filter"
              placeholder="Search sessions..."
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
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            )}
          </div>
        </div>
        <SessionList
          sessions={sessions}
          activeSessionId={activeSessionId}
          runningSessionId={runningSessionId}
          filter={localFilter}
          onCreateNew={handleCreateNew}
          onSelect={handleSelect}
          onDelete={onDelete}
        />
      </aside>
    </>
  );
}

export default memo(SessionSidebar);
