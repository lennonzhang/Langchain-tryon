import { memo, useEffect, useRef, useState } from "react";
import { shortModelName } from "../utils/models";

function ModelSelect({
  models,
  value,
  disabled,
  onChange,
  webSearch,
  onWebSearchChange,
  supportsThinking,
  thinkingMode,
  onThinkingModeChange,
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    function handleKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  const activeTags = [];
  if (webSearch) activeTags.push("Search");
  if (supportsThinking && thinkingMode) activeTags.push("Thinking");

  return (
    <div className={`model-select ${open ? "is-open" : ""}`} ref={ref}>
      <button
        type="button"
        className="model-trigger"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="model-trigger-label">{shortModelName(value)}</span>
        {activeTags.length > 0 && (
          <span className="model-trigger-tags">
            {activeTags.map((tag) => (
              <span key={tag} className="model-trigger-tag">{tag}</span>
            ))}
          </span>
        )}
        <span className="model-trigger-arrow" aria-hidden="true" />
      </button>
      {open && (
        <div className="model-menu">
          <ul className="model-menu-list" role="listbox">
            {models.map((m) => (
              <li
                key={m}
                role="option"
                aria-selected={m === value}
                className={`model-option ${m === value ? "is-selected" : ""}`}
                onClick={() => {
                  onChange(m);
                  setOpen(false);
                }}
              >
                <span className="model-option-check" aria-hidden="true">
                  {m === value && (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </span>
                <span className="model-option-text">
                  <span className="model-option-name">{shortModelName(m)}</span>
                  <span className="model-option-full">{m}</span>
                </span>
              </li>
            ))}
          </ul>

          <div className="model-menu-divider" />

          <div className="model-menu-toggles">
            <label className="model-menu-toggle">
              <span className="model-menu-toggle-info">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <span>Web Search</span>
              </span>
              <input
                type="checkbox"
                checked={webSearch}
                disabled={disabled}
                onChange={(e) => onWebSearchChange(e.target.checked)}
              />
              <span className="toggle-track" aria-hidden="true" />
            </label>

            {supportsThinking && (
              <label className="model-menu-toggle">
                <span className="model-menu-toggle-info">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z" />
                    <line x1="9" y1="21" x2="15" y2="21" />
                  </svg>
                  <span>Thinking Mode</span>
                </span>
                <input
                  type="checkbox"
                  checked={thinkingMode}
                  disabled={disabled}
                  onChange={(e) => onThinkingModeChange(e.target.checked)}
                />
                <span className="toggle-track" aria-hidden="true" />
              </label>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default memo(ModelSelect);
