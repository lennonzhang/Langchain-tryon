function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function sortByUpdatedAtDesc(a, b) {
  return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
}

export class MemorySessionRepository {
  constructor() {
    this.sessions = new Map();
  }

  async listSessions() {
    return [...this.sessions.values()].map(buildSummary).sort(sortByUpdatedAtDesc).map(clone);
  }

  async getSession(sessionId) {
    const session = this.sessions.get(sessionId);
    return session ? clone(session) : null;
  }

  async createSession(initial) {
    const now = new Date().toISOString();
    const session = {
      id: initial.id,
      title: initial.title,
      createdAt: initial.createdAt || now,
      updatedAt: initial.updatedAt || now,
      settings: { ...initial.settings },
      messages: [],
    };
    this.sessions.set(session.id, session);
    return clone(session);
  }

  async appendMessages(sessionId, messages) {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }
    session.messages.push(...messages.map(clone));
    session.updatedAt = new Date().toISOString();
  }

  async updateMessage(sessionId, messageId, updater) {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }
    session.messages = session.messages.map((message) => {
      if (message.id !== messageId) {
        return message;
      }
      return updater(clone(message));
    });
    session.updatedAt = new Date().toISOString();
  }

  async updateSessionMeta(sessionId, patch) {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Session not found: ${sessionId}`);
    }
    Object.assign(session, patch);
    session.updatedAt = patch.updatedAt || new Date().toISOString();
  }

  async deleteSession(sessionId) {
    this.sessions.delete(sessionId);
  }
}

function buildSummary(session) {
  const lastAssistantMessage = [...session.messages].reverse().find((msg) => {
    if (msg.role === "assistant") {
      return Boolean(msg.content);
    }
    if (msg.role === "assistant_stream") {
      return Boolean(msg.answer) && (msg.status === "done" || msg.status === "failed");
    }
    return false;
  });

  const preview = lastAssistantMessage
    ? lastAssistantMessage.role === "assistant"
      ? lastAssistantMessage.content
      : lastAssistantMessage.answer
    : "";

  return {
    id: session.id,
    title: session.title,
    updatedAt: session.updatedAt,
    lastMessagePreview: toPreview(preview),
    model: session.settings.model,
    flags: {
      webSearch: Boolean(session.settings.webSearch),
      thinkingMode: Boolean(session.settings.thinkingMode),
    },
  };
}

function toPreview(text) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  if (!clean) return "";
  return clean.length > 80 ? `${clean.slice(0, 80)}...` : clean;
}
