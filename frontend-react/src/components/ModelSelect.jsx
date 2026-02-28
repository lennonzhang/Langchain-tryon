import { useEffect, useRef, useState } from "react";
import { shortModelName } from "../utils/models";

export default function ModelSelect({ models, value, disabled, onChange }) {
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
        <span className="model-trigger-arrow" aria-hidden="true" />
      </button>
      {open && (
        <ul className="model-menu" role="listbox">
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
                {m === value ? "✓" : ""}
              </span>
              <span className="model-option-text">
                <span className="model-option-name">{shortModelName(m)}</span>
                <span className="model-option-full">{m}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
