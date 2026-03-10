import { memo, useState } from "react";
import CollapsibleSection from "./CollapsibleSection";
import RichBlock from "./RichBlock";
import ErrorBoundary from "./ErrorBoundary";
import CopyButton from "./CopyButton";

const richBlockFallback = (
  <div className="assistant-body" style={{ color: "var(--error, #c00)", fontStyle: "italic" }}>
    Failed to render content.
  </div>
);

const questionIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="10" />
    <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

const answeredIcon = (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6L9 17l-5-5" />
  </svg>
);

function ClarificationFreeInput({ onSubmit, disabled }) {
  const [text, setText] = useState("");
  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (trimmed && !disabled) {
      onSubmit?.(trimmed);
      setText("");
    }
  };
  return (
    <form className="clarification-free-input" onSubmit={handleSubmit}>
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type your answer..."
        disabled={disabled}
        aria-label="Free-text clarification input"
      />
      <button type="submit" disabled={disabled || !text.trim()} aria-label="Submit answer">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M5 12h14" />
          <path d="M12 5l7 7-7 7" />
        </svg>
      </button>
    </form>
  );
}

function StreamMessage({
  msg,
  showTyping,
  isCurrentRequestMessage = false,
  onSelectClarificationOption,
  canSubmitClarification = true,
}) {
  const isStreaming = msg.status === "streaming";
  const clarification = msg.clarification;
  const isAnswered = clarification?.answered;
  const interactionsDisabled = !canSubmitClarification || isAnswered || typeof onSelectClarificationOption !== "function";

  return (
    <div className={`msg assistant stream${msg.status === "done" ? " stream-done" : ""}`}>
      {msg.search.state !== "hidden" && (
        <CollapsibleSection
          key={`${msg.id}-search-${msg.search.state}`}
          title="Search"
          className="search"
          defaultOpen={msg.search.state === "loading"}
        >
          <div data-testid="search-panel">
            <div className="assistant-body">
              {msg.search.state === "loading" && (
                <span className="search-loading">Searching: &ldquo;{msg.search.query}&rdquo;...</span>
              )}
              {msg.search.state === "error" && (
                <span className="search-error">Search failed: {msg.search.error}</span>
              )}
              {msg.search.state === "done" && msg.search.results.length === 0 && (
                <span className="search-empty">No results found</span>
              )}
              {msg.search.state === "done" && msg.search.results.length > 0 && (
                <div className="search-results">
                  {msg.search.results.map((item, idx) => (
                    <div className="search-item" key={`${msg.id}-s-${idx}`}>
                      [{idx + 1}]{" "}
                      <a href={item.url} target="_blank" rel="noreferrer noopener">
                        {item.title || item.url}
                      </a>
                      {item.snippet && <div className="search-snippet">{item.snippet}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </CollapsibleSection>
      )}

      {msg.usageLines.length > 0 && (
        <CollapsibleSection title="Context Usage" className="usage" defaultOpen={false}>
          <div data-testid="usage-panel">
            <div className="assistant-body">
              {msg.usageLines.map((line, idx) => (
                <div className="agent-loading" key={`${msg.id}-u-${idx}`}>
                  {line}
                </div>
              ))}
            </div>
          </div>
        </CollapsibleSection>
      )}

      {msg.reasoning && (
        <CollapsibleSection
          key={`${msg.id}-reasoning-${isCurrentRequestMessage ? "current" : "history"}`}
          title="Reasoning"
          className="reasoning"
          defaultOpen={isCurrentRequestMessage}
        >
          <div data-testid="reasoning-panel">
            <ErrorBoundary key={`${msg.id}-reasoning`} fallback={richBlockFallback}>
              <RichBlock className="assistant-body" text={msg.reasoning} streaming={isStreaming} />
            </ErrorBoundary>
          </div>
        </CollapsibleSection>
      )}

      {clarification && (
        <div className={`assistant-section clarification${isAnswered ? " clarification-answered" : ""}`}>
          <div className="assistant-title">
            {isAnswered ? answeredIcon : questionIcon}
            {isAnswered ? "Answered" : "Need Your Input"}
          </div>
          <div className="clarification-body">
            <div className="assistant-body">{clarification.question}</div>
            {clarification.options?.length > 0 && (
              <div className="clarification-options" role="group" aria-label="Clarification options">
                {clarification.options.map((option, index) => {
                  const descId = option.description ? `${msg.id}-opt-desc-${index}` : undefined;
                  return (
                    <button
                      key={`${msg.id}-opt-${index}`}
                      type="button"
                      className="clarification-option"
                      disabled={interactionsDisabled}
                      aria-disabled={interactionsDisabled}
                      aria-describedby={descId}
                      onClick={() => onSelectClarificationOption?.(option.label)}
                    >
                      <span>{option.label}</span>
                      {option.description && <small id={descId}>{option.description}</small>}
                    </button>
                  );
                })}
              </div>
            )}
            {clarification.allowFreeText && !isAnswered && (
              <>
                {clarification.options?.length > 0 && (
                  <div className="clarification-divider">
                    <span>or type your answer</span>
                  </div>
                )}
                <ClarificationFreeInput
                  onSubmit={onSelectClarificationOption}
                  disabled={!canSubmitClarification || typeof onSelectClarificationOption !== "function"}
                />
              </>
            )}
          </div>
        </div>
      )}

      {!clarification && (
        <div className="assistant-section answer">
          <div className="assistant-title">
            Answer
            {!isStreaming && msg.answer && <CopyButton text={msg.answer} />}
          </div>
          <ErrorBoundary key={`${msg.id}-answer`} fallback={richBlockFallback}>
            <RichBlock className="assistant-body" text={msg.answer} streaming={isStreaming} />
          </ErrorBoundary>
          {showTyping && (
            <span className="typing-dots" aria-label="Typing">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default memo(StreamMessage);
