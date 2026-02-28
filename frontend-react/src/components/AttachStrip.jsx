import { MAX_ATTACHMENTS } from "../utils/media";

export default function AttachStrip({ attachments, fileInputRef, isPending, onRemove, onFilesSelected }) {
  return (
    <div className="attach-strip" data-testid="attach-strip">
      {attachments.map((att) => (
        <div className="attach-thumb" key={att.id}>
          {att.type === "image" ? (
            <img src={att.dataUrl} alt={att.name} />
          ) : att.thumbUrl ? (
            <div className="attach-video-frame" title={att.name}>
              <img src={att.thumbUrl} alt={att.name} />
              <span className="attach-video-play" aria-hidden="true">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="6 3 20 12 6 21 6 3" />
                </svg>
              </span>
            </div>
          ) : (
            <div className="attach-video-icon" title={att.name}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              <span className="attach-video-name">{att.name}</span>
            </div>
          )}
          <button
            type="button"
            className="attach-remove"
            onClick={() => onRemove(att.id)}
            aria-label={`Remove ${att.name}`}
            disabled={isPending}
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <line x1="2" y1="2" x2="8" y2="8" />
              <line x1="8" y1="2" x2="2" y2="8" />
            </svg>
          </button>
        </div>
      ))}

      {attachments.length < MAX_ATTACHMENTS && (
        <button
          type="button"
          className="attach-add-btn"
          disabled={isPending}
          title="Add image or video"
          aria-label="Add file"
          onClick={() => fileInputRef.current?.click()}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,video/*"
        multiple
        hidden
        disabled={isPending}
        onChange={(event) => onFilesSelected(event.target.files)}
      />
    </div>
  );
}
