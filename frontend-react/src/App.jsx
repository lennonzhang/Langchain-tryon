import { useCallback, useEffect, useRef, useState } from "react";
import { useShallow } from "zustand";
import { useAttachments } from "./hooks/useAttachments";
import { useAutoFollowScroll } from "./hooks/useAutoFollowScroll";
import { useResponsiveSessionSidebar } from "./hooks/useResponsiveSessionSidebar";
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
  const composerFormRef = useRef(null);
  const { models, model, setModel, supportsThinking, supportsMedia } = useCapabilitiesQuery();
  const [webSearch, setWebSearch] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(true);

  const { attachments, fileInputRef, handleFilesSelected, removeAttachment, clearAttachments } =
    useAttachments(supportsMedia);

  const sessionListQuery = useSessionListQuery();
  const sessions = sessionListQuery.data || [];
  const { appShellRef, sidebarRef, isSessionOverlay } = useResponsiveSessionSidebar();

  const {
    sidebarOpen, filter, activeSessionId, draftsBySessionId, requestIdBySessionId,
    toggleSidebar, setSidebarOpen, setFilter, setActiveSessionId, setDraft, reset,
  } = useChatUiStore(
    useShallow((state) => ({
      sidebarOpen: state.sidebarOpen,
      filter: state.filter,
      activeSessionId: state.activeSessionId,
      draftsBySessionId: state.draftsBySessionId,
      requestIdBySessionId: state.requestIdBySessionId,
      toggleSidebar: state.toggleSidebar,
      setSidebarOpen: state.setSidebarOpen,
      setFilter: state.setFilter,
      setActiveSessionId: state.setActiveSessionId,
      setDraft: state.setDraft,
      reset: state.reset,
    }))
  );

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

  useEffect(() => {
    if (!isSessionOverlay && sidebarOpen) {
      setSidebarOpen(false);
    }
  }, [isSessionOverlay, setSidebarOpen, sidebarOpen]);

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
  const isSidebarOpen = isSessionOverlay && sidebarOpen;
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
  const handleInputChange = useCallback(
    (value) => setDraft(activeSessionId, value),
    [setDraft, activeSessionId]
  );
  const handleSelectClarificationOption = useCallback((label) => {
    const text = String(label || "").trim();
    if (!text) return;
    if (useChatUiStore.getState().pendingBySessionId[activeSessionId]) return;
    setDraft(activeSessionId, text);
    queueMicrotask(() => composerFormRef.current?.requestSubmit());
  }, [activeSessionId, setDraft]);

  return (
    <div
      ref={appShellRef}
      className={`app-shell ${isSessionOverlay ? "is-session-overlay" : ""}`}
    >
      <SessionSidebar
        sidebarRef={sidebarRef}
        sessions={sessions}
        activeSessionId={activeSessionId}
        runningSessionId={runningSessionId}
        filter={filter}
        isOpen={isSidebarOpen}
        overlayMode={isSessionOverlay}
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
              aria-expanded={isSidebarOpen}
              aria-label="Open sessions panel"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
            </button>
            <div className="header-copy">
              <h1>{isDraftSession ? "New Chat" : activeSession?.title || "Chat"}</h1>
              <p>{shortModelName(model)}</p>
            </div>
          </div>
        </header>

        <div className={`status-bar ${isGlobalPending ? "is-busy" : ""}`}>
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
          onSelectClarificationOption={handleSelectClarificationOption}
          canSubmitClarification={!isGlobalPending}
        />

        <Composer
          formRef={composerFormRef}
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
          onInputChange={handleInputChange}
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
