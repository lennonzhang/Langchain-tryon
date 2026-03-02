import { useEffect, useRef, useState } from "react";
import { useCapabilities } from "./hooks/useCapabilities";
import { useAttachments } from "./hooks/useAttachments";
import { useChatStream } from "./hooks/useChatStream";
import MessageList from "./components/MessageList";
import Composer from "./components/Composer";
import { shortModelName, CONNECTED_TEXT } from "./utils/models";
import { CHAT_V2_LAYOUT } from "./shared/lib/features";
import { AppProviders } from "./app/AppProviders";
import { useCapabilitiesQuery } from "./features/chat/useCapabilitiesQuery";
import { useSessionDetailQuery, useSessionListQuery, useDeleteSessionMutation } from "./features/sessions/useSessions";
import SessionSidebar from "./features/sessions/SessionSidebar";
import { NEW_SESSION_KEY, useChatUiStore } from "./shared/store/chatUiStore";
import { useSendMessage } from "./features/chat/useSendMessage";

export { shortModelName };

function LegacyApp() {
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
      <div className="chat">
        <header className="header">
          <div className="header-main">
            <div className="header-kicker">LangChain + NVIDIA</div>
            <h1>Streaming Chat Studio</h1>
            <p>Web Search, Thinking &amp; streaming Reasoning.</p>
          </div>
        </header>
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
      </div>
    </div>
  );
}

function AppContent() {
  const { models, model, setModel, supportsThinking, supportsMedia } = useCapabilitiesQuery();
  const [webSearch, setWebSearch] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(true);

  const { attachments, fileInputRef, handleFilesSelected, removeAttachment, clearAttachments } =
    useAttachments(supportsMedia);

  const messagesRef = useRef(null);

  const sessionListQuery = useSessionListQuery();
  const sessions = sessionListQuery.data || [];

  const sidebarOpen = useChatUiStore((state) => state.sidebarOpen);
  const filter = useChatUiStore((state) => state.filter);
  const activeSessionId = useChatUiStore((state) => state.activeSessionId);
  const draftsBySessionId = useChatUiStore((state) => state.draftsBySessionId);
  const pendingBySessionId = useChatUiStore((state) => state.pendingBySessionId);
  const requestIdBySessionId = useChatUiStore((state) => state.requestIdBySessionId);
  const setSidebarOpen = useChatUiStore((state) => state.setSidebarOpen);
  const setFilter = useChatUiStore((state) => state.setFilter);
  const setActiveSessionId = useChatUiStore((state) => state.setActiveSessionId);
  const setDraft = useChatUiStore((state) => state.setDraft);
  const reset = useChatUiStore((state) => state.reset);

  useEffect(() => {
    return () => {
      reset();
    };
  }, [reset]);

  useEffect(() => {
    if (!activeSessionId && sessions.length > 0) {
      setActiveSessionId(sessions[0].id);
    }
  }, [activeSessionId, sessions, setActiveSessionId]);

  const activeSessionQuery = useSessionDetailQuery(activeSessionId);
  const activeSession = activeSessionQuery.data;

  const deleteSessionMutation = useDeleteSessionMutation();

  const onSubmit = useSendMessage({
    model,
    webSearch,
    thinkingMode,
    supportsThinking,
    supportsMedia,
    attachments,
    clearAttachments,
  });

  const activeKey = activeSessionId || NEW_SESSION_KEY;
  const input = draftsBySessionId[activeKey] || "";
  const isPending = activeSessionId && activeSessionId !== NEW_SESSION_KEY ? Boolean(pendingBySessionId[activeSessionId]) : false;
  const currentRequestId =
    activeSessionId && activeSessionId !== NEW_SESSION_KEY ? requestIdBySessionId[activeSessionId] || null : null;
  const messages = activeSession?.messages?.length
    ? activeSession.messages
    : [{ id: "connected", role: "assistant", content: CONNECTED_TEXT }];

  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
    if (!isNearBottom) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [messages]);

  return (
    <div className={`app-shell ${isPending ? "is-pending" : ""}`}>
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        filter={filter}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        onFilterChange={setFilter}
        onCreateNew={() => setActiveSessionId(NEW_SESSION_KEY)}
        onSelect={(sessionId) => setActiveSessionId(sessionId)}
        onDelete={async (sessionId) => {
          await deleteSessionMutation.mutateAsync(sessionId);
          if (activeSessionId === sessionId) {
            setActiveSessionId(null);
          }
        }}
      />

      <div className="chat">
        <header className="header">
          <div className="header-main">
            <div className="header-kicker">LangChain + NVIDIA</div>
            <h1>Streaming Chat Studio</h1>
            <p>Conversation workspace with session history.</p>
          </div>
          <div className="header-meta">
            <span className="meta-pill">SSE Streaming</span>
            <span className="meta-pill">Session History</span>
            <span className="meta-pill">Robust Tests</span>
          </div>
        </header>

        <div className="status-bar">
          <span className={`status-dot ${isPending ? "busy" : ""}`} />
          <span>{isPending ? "Generating response..." : "Ready"}</span>
        </div>

        <MessageList messages={messages} isPending={isPending} currentRequestId={currentRequestId} ref={messagesRef} />

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
          onInputChange={(value) => setDraft(activeSessionId, value)}
          isPending={isPending}
          onSubmit={onSubmit}
        />
      </div>
    </div>
  );
}

export default function App() {
  if (!CHAT_V2_LAYOUT) {
    return <LegacyApp />;
  }

  return (
    <AppProviders>
      <AppContent />
    </AppProviders>
  );
}
