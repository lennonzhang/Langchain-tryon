import { create } from "zustand";

export const NEW_SESSION_KEY = "__new_session__";

export const useChatUiStore = create((set, get) => ({
  sidebarOpen: false,
  filter: "",
  activeSessionId: null,
  draftsBySessionId: {},
  pendingBySessionId: {},
  requestIdBySessionId: {},
  lastErrorBySessionId: {},

  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setFilter: (filter) => set({ filter }),

  setActiveSessionId: (sessionId) => set({ activeSessionId: sessionId }),

  setDraft: (sessionId, draft) =>
    set((state) => ({
      draftsBySessionId: {
        ...state.draftsBySessionId,
        [sessionId || NEW_SESSION_KEY]: draft,
      },
    })),

  getDraft: (sessionId) => {
    const key = sessionId || NEW_SESSION_KEY;
    return get().draftsBySessionId[key] || "";
  },

  startRequest: (sessionId, requestId) =>
    set((state) => ({
      pendingBySessionId: { ...state.pendingBySessionId, [sessionId]: true },
      requestIdBySessionId: { ...state.requestIdBySessionId, [sessionId]: requestId },
      lastErrorBySessionId: { ...state.lastErrorBySessionId, [sessionId]: "" },
    })),

  finishRequest: (sessionId) =>
    set((state) => ({
      pendingBySessionId: { ...state.pendingBySessionId, [sessionId]: false },
    })),

  failRequest: (sessionId, errorText) =>
    set((state) => ({
      pendingBySessionId: { ...state.pendingBySessionId, [sessionId]: false },
      lastErrorBySessionId: { ...state.lastErrorBySessionId, [sessionId]: errorText },
    })),

  isCurrentRequest: (sessionId, requestId) => get().requestIdBySessionId[sessionId] === requestId,

  reset: () =>
    set({
      sidebarOpen: false,
      filter: "",
      activeSessionId: null,
      draftsBySessionId: {},
      pendingBySessionId: {},
      requestIdBySessionId: {},
      lastErrorBySessionId: {},
    }),
}));
