import { memo } from "react";
import CollapsibleSection from "./CollapsibleSection";
import RichBlock from "./RichBlock";
import ErrorBoundary from "./ErrorBoundary";
import CopyButton from "./CopyButton";

const richBlockFallback = (
  <div className="assistant-body" style={{ color: "var(--error, #c00)", fontStyle: "italic" }}>
    Failed to render content.
  </div>
);

function StreamMessage({ msg, showTyping, isCurrentRequestMessage = false }) {
  const isStreaming = msg.status === "streaming";
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
    </div>
  );
}

export default memo(StreamMessage);
