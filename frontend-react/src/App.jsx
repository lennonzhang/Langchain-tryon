import { useCallback, useEffect, useState } from "react";
import { useAttachments } from "./hooks/useAttachments";
import { useAutoFollowScroll } from "./hooks/useAutoFollowScroll";
import MessageList from "./components/MessageList";
import Composer from "./components/Composer";
import ErrorBoundary from "./components/ErrorBoundary";
import { shortModelName, CONNECTED_TEXT } from "./utils/models";
import { AppProviders } from "./app/AppProviders";
import { useCapabilitiesQuery } from "./features/chat/useCapabilitiesQuery";
import { useSessionDetailQuery, useSessionListQuery, useDeleteSessionMutation } from "./features/sessions/useSessions";
import SessionSidebar from "./features/sessions/SessionSidebar";
import { NEW_SESSION_KEY, useChatUiStore, selectRunningSessionId } from "./shared/store/chatUiStore";
import { useSendMessage } from "./features/chat/useSendMessage";

export { shortModelName };

function AppContent() {
  const autoScrollThresholdPx = 150;
  const { models, model, setModel, supportsThinking, supportsMedia } = useCapabilitiesQuery();
  const [webSearch, setWebSearch] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(true);

  const { attachments, fileInputRef, handleFilesSelected, removeAttachment, clearAttachments } =
    useAttachments(supportsMedia);

  const sessionListQuery = useSessionListQuery();
  const sessions = sessionListQuery.data || [];

  const sidebarOpen = useChatUiStore((state) => state.sidebarOpen);
  const filter = useChatUiStore((state) => state.filter);
  const activeSessionId = useChatUiStore((state) => state.activeSessionId);
  const draftsBySessionId = useChatUiStore((state) => state.draftsBySessionId);
  const requestIdBySessionId = useChatUiStore((state) => state.requestIdBySessionId);
  const toggleSidebar = useChatUiStore((state) => state.toggleSidebar);
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
  const isDraftSession = activeSessionId === NEW_SESSION_KEY;
  const activeSession = isDraftSession ? null : activeSessionQuery.data;

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
  const runningSessionId = useChatUiStore(selectRunningSessionId);
  const isGlobalPending = Boolean(runningSessionId);
  const isActiveRunningSession =
    Boolean(activeSessionId) &&
    activeSessionId !== NEW_SESSION_KEY &&
    activeSessionId === runningSessionId;
  const isSessionStreaming = isActiveRunningSession;
  const currentRequestId =
    activeSessionId && activeSessionId !== NEW_SESSION_KEY ? requestIdBySessionId[activeSessionId] || null : null;
  const messages = activeSession?.messages?.length
    ? activeSession.messages
    : [{ id: "connected", role: "assistant", content: CONNECTED_TEXT }];
  const isSessionDetailLoading = !isDraftSession && activeSessionQuery.isLoading;

  const { containerRef: messagesRef, handleScroll: handleMessagesScroll } = useAutoFollowScroll({
    thresholdPx: autoScrollThresholdPx,
    watchValue: messages,
  });

  const handleToggleSidebar = useCallback(() => toggleSidebar(), [toggleSidebar]);
  const handleOpenSidebar = useCallback(() => setSidebarOpen(true), [setSidebarOpen]);
  const handleCloseSidebar = useCallback(() => setSidebarOpen(false), [setSidebarOpen]);
  const handleCreateNew = useCallback(() => setActiveSessionId(NEW_SESSION_KEY), [setActiveSessionId]);
  const handleSelectSession = useCallback((id) => setActiveSessionId(id), [setActiveSessionId]);
  const handleDeleteSession = useCallback(async (sessionId) => {
    // Data-layer guard: prevent deleting a session with an active stream.
    if (useChatUiStore.getState().pendingBySessionId[sessionId]) return;
    await deleteSessionMutation.mutateAsync(sessionId);
    if (useChatUiStore.getState().activeSessionId === sessionId) {
      setActiveSessionId(null);
    }
  }, [deleteSessionMutation, setActiveSessionId]);

  return (
    <div className="app-shell">
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        runningSessionId={runningSessionId}
        filter={filter}
        isOpen={sidebarOpen}
        onToggle={handleToggleSidebar}
        onClose={handleCloseSidebar}
        onFilterChange={setFilter}
        onCreateNew={handleCreateNew}
        onSelect={handleSelectSession}
        onDelete={handleDeleteSession}
      />

      <div className="chat">
        <header className="header">
          <div className="header-main">
            <button
              type="button"
              className="header-sessions-btn"
              onClick={handleOpenSidebar}
              aria-controls="session-sidebar"
              aria-expanded={sidebarOpen}
              aria-label="Open sessions panel"
            >
              Sessions
            </button>
            <div className="header-copy">
              <h1>Chat Workspace</h1>
              <p>Session-based streaming chat.</p>
            </div>
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
        </div>

        <MessageList
          messages={messages}
          isPending={isSessionStreaming}
          currentRequestId={currentRequestId}
          ref={messagesRef}
          onScroll={handleMessagesScroll}
          loading={isSessionDetailLoading}
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
          showStop={isActiveRunningSession}
          onStop={stopActiveSession}
          pendingHint={isGlobalPending && !isActiveRunningSession ? "Another session is generating. Open it to stop." : ""}
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
