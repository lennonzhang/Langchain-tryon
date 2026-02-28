import { useState } from "react";
import { useCapabilities } from "./hooks/useCapabilities";
import { useAttachments } from "./hooks/useAttachments";
import { useChatStream } from "./hooks/useChatStream";
import MessageList from "./components/MessageList";
import Composer from "./components/Composer";

export { shortModelName } from "./utils/models";

export default function App() {
  const { models, model, setModel, supportsThinking, supportsMedia } = useCapabilities();
  const { attachments, fileInputRef, handleFilesSelected, removeAttachment, clearAttachments } =
    useAttachments(supportsMedia);
  const [webSearch, setWebSearch] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(true);
  const { messages, input, setInput, isPending, onSubmit, messagesRef } = useChatStream({
    model,
    webSearch,
    thinkingMode,
    supportsThinking,
    supportsMedia,
    attachments,
    clearAttachments,
  });

  return (
    <div className={`wrap ${isPending ? "is-pending" : ""}`}>
      <div className="bg-orb orb-a" aria-hidden="true" />
      <div className="bg-orb orb-b" aria-hidden="true" />
      <div className="bg-orb orb-c" aria-hidden="true" />
      <div className="bg-grid" aria-hidden="true" />

      <div className="chat">
        <header className="header">
          <div className="header-main">
            <div className="header-kicker">LangChain + NVIDIA</div>
            <h1>Streaming Chat Studio</h1>
            <p>Web Search, Thinking &amp; streaming Reasoning.</p>
          </div>
          <div className="header-meta">
            <span className="meta-pill">SSE Streaming</span>
            <span className="meta-pill">Math + Markdown</span>
            <span className="meta-pill">K2.5 / QWEN3.5 / GLM5</span>
          </div>
        </header>

        <div className="status-bar">
          <span className={`status-dot ${isPending ? "busy" : ""}`} />
          <span>{isPending ? "Generating response..." : "Ready"}</span>
        </div>

        <MessageList messages={messages} isPending={isPending} ref={messagesRef} />

        <Composer
          models={models}
          model={model}
          onModelChange={setModel}
          webSearch={webSearch}
          onWebSearchChange={setWebSearch}
          supportsThinking={supportsThinking}
          thinkingMode={thinkingMode}
          onThinkingModeChange={setThinkingMode}
          supportsMedia={supportsMedia}
          attachments={attachments}
          fileInputRef={fileInputRef}
          onRemoveAttachment={removeAttachment}
          onFilesSelected={handleFilesSelected}
          input={input}
          onInputChange={setInput}
          isPending={isPending}
          onSubmit={onSubmit}
        />

        <div className="tip">
          Max output tokens fixed at 16384. K2.5, Qwen 3.5 &amp; GLM5 all support Thinking/Instant. Image/video input supported by K2.5 only.
        </div>
      </div>
    </div>
  );
}
