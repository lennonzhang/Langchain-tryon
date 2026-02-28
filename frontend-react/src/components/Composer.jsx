import ModelSelect from "./ModelSelect";
import AttachStrip from "./AttachStrip";

export default function Composer({
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
  onSubmit,
}) {
  return (
    <form className="composer" onSubmit={onSubmit}>
      <div className="settings-card">
        <div className="model-field">
          <span className="model-field-label">Model</span>
          <ModelSelect models={models} value={model} disabled={isPending} onChange={onModelChange} />
        </div>

        <div className="toggles" role="group" aria-label="chat options">
          <label className="toggle" htmlFor="searchToggle">
            <input
              type="checkbox"
              id="searchToggle"
              checked={webSearch}
              disabled={isPending}
              onChange={(event) => onWebSearchChange(event.target.checked)}
            />
            <span className="toggle-track" aria-hidden="true" />
            <span className="toggle-label">Web Search</span>
          </label>

          {supportsThinking && (
            <label className="toggle" htmlFor="thinkingToggle">
              <input
                type="checkbox"
                id="thinkingToggle"
                checked={thinkingMode}
                disabled={isPending}
                onChange={(event) => onThinkingModeChange(event.target.checked)}
              />
              <span className="toggle-track" aria-hidden="true" />
              <span className="toggle-label">Thinking Mode</span>
            </label>
          )}
        </div>
      </div>

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
            placeholder="Press Enter to send (Shift+Enter for newline)"
            required
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button id="sendBtn" type="submit" disabled={isPending} aria-label="Send">
            <svg className="send-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 2L11 13" />
              <path d="M22 2L15 22L11 13L2 9L22 2Z" />
            </svg>
          </button>
        </div>
      </div>
    </form>
  );
}
