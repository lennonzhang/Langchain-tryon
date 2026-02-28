import { useState } from "react";

export default function CollapsibleSection({ title, className, children, defaultOpen = true }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className={`assistant-section ${className} ${isOpen ? "is-open" : "is-closed"}`}>
      <button
        type="button"
        className="section-toggle"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
      >
        <span className="assistant-title">{title}</span>
        <span className={`chevron ${isOpen ? "open" : ""}`} aria-hidden="true" />
      </button>
      <div className={`section-content ${isOpen ? "expanded" : "collapsed"}`}>
        {children}
      </div>
    </div>
  );
}
