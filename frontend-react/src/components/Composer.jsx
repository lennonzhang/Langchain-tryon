import { memo } from "react";
import ModelSelect from "./ModelSelect";
import AttachStrip from "./AttachStrip";

function Composer({
  models,
  model,
  onModelChange,
  webSearch,
  onWebSearchChange,
  supportsThinking,
  thinkingMode,
  onThinkingModeChange,
  supportsMedia,
  attachments,
  fileInputRef,
  onRemoveAttachment,
  onFilesSelected,
  input,
  onInputChange,
  isPending,
  showStop = false,
  onStop,
  pendingHint,
  onSubmit,
}) {
  const stopMode = Boolean(showStop && typeof onStop === "function");
  const sendDisabled = Boolean(isPending && !stopMode);

  return (
    <form className="composer" onSubmit={onSubmit}>
      <div className="input-shell">
        {supportsMedia && (
          <AttachStrip
            attachments={attachments}
            fileInputRef={fileInputRef}
            isPending={isPending}
            onRemove={onRemoveAttachment}
            onFilesSelected={onFilesSelected}
          />
        )}

        <div className="input-row">
          <textarea
            id="input"
            value={input}
            disabled={isPending}
            placeholder={pendingHint || "Type a message... (Enter to send, Shift+Enter for newline)"}
            required
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button
            id="sendBtn"
            type={stopMode ? "button" : "submit"}
            className={stopMode ? "is-stop" : ""}
            disabled={sendDisabled}
            aria-label={stopMode ? "Stop" : "Send"}
            onClick={stopMode ? onStop : undefined}
          >
            {stopMode ? (
              <span className="stop-icon" aria-hidden="true">
                <span className="stop-square" />
              </span>
            ) : (
              <svg className="send-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2L11 13" />
                <path d="M22 2L15 22L11 13L2 9L22 2Z" />
              </svg>
            )}
          </button>
        </div>

        <div className="settings-card">
          <ModelSelect
            models={models}
            value={model}
            disabled={isPending}
            onChange={onModelChange}
            webSearch={webSearch}
            onWebSearchChange={onWebSearchChange}
            supportsThinking={supportsThinking}
            thinkingMode={thinkingMode}
            onThinkingModeChange={onThinkingModeChange}
          />
        </div>
      </div>
    </form>
  );
}

export default memo(Composer);
