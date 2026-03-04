import { useCallback, useEffect, useRef, useState } from "react";
import { useAttachments } from "./hooks/useAttachments";
import MessageList from "./components/MessageList";
import Composer from "./components/Composer";
import ErrorBoundary from "./components/ErrorBoundary";
import { shortModelName, CONNECTED_TEXT } from "./utils/models";
import { AppProviders } from "./app/AppProviders";
import { useCapabilitiesQuery } from "./features/chat/useCapabilitiesQuery";
import { useSessionDetailQuery, useSessionListQuery, useDeleteSessionMutation } from "./features/sessions/useSessions";
import SessionSidebar from "./features/sessions/SessionSidebar";
import { NEW_SESSION_KEY, useChatUiStore } from "./shared/store/chatUiStore";
import { useSendMessage } from "./features/chat/useSendMessage";

export { shortModelName };

function AppContent() {
  const autoScrollThresholdPx = 150;
  const { models, model, setModel, supportsThinking, supportsMedia } = useCapabilitiesQuery();
  const [webSearch, setWebSearch] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(true);

  const { attachments, fileInputRef, handleFilesSelected, removeAttachment, clearAttachments } =
    useAttachments(supportsMedia);

  const messagesRef = useRef(null);
  const stickToBottomRef = useRef(true);

  const sessionListQuery = useSessionListQuery();
  const sessions = sessionListQuery.data || [];

  const sidebarOpen = useChatUiStore((state) => state.sidebarOpen);
  const filter = useChatUiStore((state) => state.filter);
  const activeSessionId = useChatUiStore((state) => state.activeSessionId);
  const draftsBySessionId = useChatUiStore((state) => state.draftsBySessionId);
  const pendingBySessionId = useChatUiStore((state) => state.pendingBySessionId);
  const requestIdBySessionId = useChatUiStore((state) => state.requestIdBySessionId);
  const toggleSidebar = useChatUiStore((state) => state.toggleSidebar);
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

  const { onSubmit, stopActiveSession } = useSendMessage({
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
  const runningSessionId =
    Object.entries(pendingBySessionId).find(([, pending]) => Boolean(pending))?.[0] || null;
  const isGlobalPending = Boolean(runningSessionId);
  const isActiveRunningSession =
    Boolean(activeSessionId) &&
    activeSessionId !== NEW_SESSION_KEY &&
    activeSessionId === runningSessionId;
  const isPending = isActiveRunningSession;
  const currentRequestId =
    activeSessionId && activeSessionId !== NEW_SESSION_KEY ? requestIdBySessionId[activeSessionId] || null : null;
  const messages = activeSession?.messages?.length
    ? activeSession.messages
    : [{ id: "connected", role: "assistant", content: CONNECTED_TEXT }];

  const handleMessagesScroll = useCallback((event) => {
    const el = event?.currentTarget || messagesRef.current;
    if (!el) return;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceToBottom <= autoScrollThresholdPx;
  }, []);

  const handleToggleSidebar = useCallback(() => toggleSidebar(), [toggleSidebar]);
  const handleCreateNew = useCallback(() => setActiveSessionId(NEW_SESSION_KEY), [setActiveSessionId]);
  const handleSelectSession = useCallback((id) => setActiveSessionId(id), [setActiveSessionId]);
  const handleDeleteSession = useCallback(async (sessionId) => {
    await deleteSessionMutation.mutateAsync(sessionId);
    if (useChatUiStore.getState().activeSessionId === sessionId) {
      setActiveSessionId(null);
    }
  }, [deleteSessionMutation, setActiveSessionId]);

  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;
    if (!stickToBottomRef.current) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [messages]);

  return (
    <div className={`app-shell ${isGlobalPending ? "is-pending" : ""}`}>
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        runningSessionId={runningSessionId}
        filter={filter}
        isOpen={sidebarOpen}
        onToggle={handleToggleSidebar}
        onFilterChange={setFilter}
        onCreateNew={handleCreateNew}
        onSelect={handleSelectSession}
        onDelete={handleDeleteSession}
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
          <span className={`status-dot ${isGlobalPending ? "busy" : ""}`} />
          <span>
            {!isGlobalPending
              ? "Ready"
              : isActiveRunningSession
                ? "Generating response..."
                : "Response running in another session. Open it to stop."}
          </span>
          {isActiveRunningSession && (
            <button type="button" className="status-stop" onClick={stopActiveSession}>
              Stop
            </button>
          )}
        </div>

        <MessageList
          messages={messages}
          isPending={isPending}
          currentRequestId={currentRequestId}
          ref={messagesRef}
          onScroll={handleMessagesScroll}
          loading={activeSessionQuery.isLoading}
        />

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
          isPending={isGlobalPending}
          onSubmit={onSubmit}
        />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AppProviders>
      <ErrorBoundary>
        <AppContent />
      </ErrorBoundary>
    </AppProviders>
  );
}
