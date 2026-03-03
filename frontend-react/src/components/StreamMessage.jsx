import { memo } from "react";
import CollapsibleSection from "./CollapsibleSection";
import RichBlock from "./RichBlock";

function StreamMessage({ msg, showTyping }) {
  return (
    <div className={`msg assistant stream${msg.status === "done" ? " stream-done" : ""}`}>
      {msg.search.state !== "hidden" && (
        <CollapsibleSection title="Search" className="search" defaultOpen={true}>
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
        <CollapsibleSection title="Reasoning" className="reasoning" defaultOpen={true}>
          <div data-testid="reasoning-panel">
            <RichBlock className="assistant-body" text={msg.reasoning} />
          </div>
        </CollapsibleSection>
      )}

      <div className="assistant-section answer">
        <div className="assistant-title">Answer</div>
        <RichBlock className="assistant-body" text={msg.answer} />
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
