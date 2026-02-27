import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { parseEventStream } from "./stream";

const MODELS = ["moonshotai/kimi-k2.5", "qwen/qwen3.5-397b-a17b", "z-ai/glm5"];
const MAX_ATTACHMENTS = 5;
const CONNECTED_TEXT = "已连接，输入你的问题开始对话。";

export function modelSupportsThinking(model) {
  return model.startsWith("moonshotai/") || model.startsWith("qwen/") || model.startsWith("z-ai/");
}

export function modelSupportsMediaInput(model) {
  return model.startsWith("moonshotai/");
}

export function shortModelName(model) {
  const idx = model.lastIndexOf("/");
  return idx >= 0 ? model.slice(idx + 1) : model;
}

function toSafeHtml(source) {
  const text = typeof source === "string" ? source : String(source ?? "");
  const parsed = marked.parse(text, {
    gfm: true,
    breaks: true,
    mangle: false,
    headerIds: false
  });
  return DOMPurify.sanitize(parsed, { USE_PROFILES: { html: true } });
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(new Error(`Failed to read: ${file.name}`));
    reader.readAsDataURL(file);
  });
}

function extractVideoFrame(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.muted = true;
    video.preload = "auto";
    video.playsInline = true;

    let done = false;
    const finish = (value) => {
      if (done) return;
      done = true;
      URL.revokeObjectURL(url);
      resolve(value);
    };

    const drawFrame = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth || 160;
        canvas.height = video.videoHeight || 90;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          finish("");
          return;
        }
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        finish(canvas.toDataURL("image/jpeg", 0.7));
      } catch {
        finish("");
      }
    };

    video.addEventListener("error", () => {
      finish("");
    }, { once: true });

    video.addEventListener("loadeddata", () => {
      drawFrame();
    }, { once: true });

    // Prevent edge-case hangs when media metadata/data never becomes available.
    setTimeout(() => finish(""), 2500);

    video.src = url;
  });
}

let _attachId = 0;
function nextAttachId() {
  _attachId += 1;
  return _attachId;
}

/* ---- Sub-components ---- */

function RichBlock({ text, className }) {
  const html = useMemo(() => toSafeHtml(text), [text]);

  useEffect(() => {
    if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
      window.MathJax.typesetPromise().catch(() => {});
    }
  }, [html]);

  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}

function CollapsibleSection({ title, className, children, defaultOpen = true }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className={`assistant-section ${className} ${isOpen ? "is-open" : "is-closed"}`}>
      <button
        type="button"
        className="section-toggle"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
      >
        <span className="assistant-title">{title}</span>
        <span className={`chevron ${isOpen ? "open" : ""}`} aria-hidden="true" />
      </button>
      <div className={`section-content ${isOpen ? "expanded" : "collapsed"}`}>
        {children}
      </div>
    </div>
  );
}

function ModelSelect({ models, value, disabled, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    function handleKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  return (
    <div className={`model-select ${open ? "is-open" : ""}`} ref={ref}>
      <button
        type="button"
        className="model-trigger"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="model-trigger-label">{shortModelName(value)}</span>
        <span className="model-trigger-arrow" aria-hidden="true" />
      </button>
      {open && (
        <ul className="model-menu" role="listbox">
          {models.map((m) => (
            <li
              key={m}
              role="option"
              aria-selected={m === value}
              className={`model-option ${m === value ? "is-selected" : ""}`}
              onClick={() => {
                onChange(m);
                setOpen(false);
              }}
            >
              <span className="model-option-check" aria-hidden="true">
                {m === value ? "✓" : ""}
              </span>
              <span className="model-option-text">
                <span className="model-option-name">{shortModelName(m)}</span>
                <span className="model-option-full">{m}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ---- Main App ---- */

export default function App() {
  const fileInputRef = useRef(null);
  const messagesRef = useRef(null);
  const idRef = useRef(2);

  const [messages, setMessages] = useState([{ id: 1, role: "assistant", content: CONNECTED_TEXT }]);
  const [history, setHistory] = useState([]);
  const [input, setInput] = useState("");
  const [model, setModel] = useState(MODELS[0]);
  const [webSearch, setWebSearch] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(true);
  const [isPending, setPending] = useState(false);
  const [attachments, setAttachments] = useState([]);

  const supportsThinking = modelSupportsThinking(model);
  const supportsMedia = modelSupportsMediaInput(model);

  useEffect(() => {
    if (!supportsMedia) {
      setAttachments([]);
    }
  }, [supportsMedia]);

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages]);

  function nextId() {
    const id = idRef.current;
    idRef.current += 1;
    return id;
  }

  function updateStreamMessage(streamId, updater) {
    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id !== streamId || msg.role !== "assistant_stream") return msg;
        return updater(msg);
      })
    );
  }

  const handleFilesSelected = useCallback(
    async (fileList) => {
      const files = Array.from(fileList || []);
      if (files.length === 0) return;

      const remaining = MAX_ATTACHMENTS - attachments.length;
      const batch = files.slice(0, Math.max(0, remaining));

      const newItems = [];
      for (const file of batch) {
        try {
          const dataUrl = await readFileAsDataUrl(file);
          const type = file.type.startsWith("video/") ? "video" : "image";
          let thumbUrl = "";
          if (type === "video") {
            thumbUrl = await extractVideoFrame(file);
          }
          newItems.push({ id: nextAttachId(), file, dataUrl, type, name: file.name, thumbUrl });
        } catch {
          // skip unreadable files
        }
      }

      if (newItems.length > 0) {
        setAttachments((prev) => [...prev, ...newItems]);
      }

      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [attachments.length]
  );

  function removeAttachment(id) {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }

  async function onSubmit(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || isPending) return;

    const effectiveThinking = supportsThinking ? thinkingMode : true;
    const mediaUrls = supportsMedia ? attachments.map((a) => a.dataUrl) : [];
    const tags = [shortModelName(model)];
    if (webSearch) tags.push("Search");
    if (supportsThinking) tags.push(effectiveThinking ? "Thinking" : "Instant");
    if (mediaUrls.length > 0) tags.push(`Media x${mediaUrls.length}`);

    const userId = nextId();
    const streamId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: `[${tags.join("] [")}]\n${text}` },
      {
        id: streamId,
        role: "assistant_stream",
        search: { state: "hidden", query: "", results: [], error: "" },
        usageLines: [],
        reasoning: "",
        answer: "正在思考..."
      }
    ]);

    setInput("");
    setAttachments([]);
    setPending(true);

    let answer = "";
    try {
      const resp = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history,
          model,
          web_search: webSearch,
          thinking_mode: effectiveThinking,
          images: mediaUrls
        })
      });

      if (!resp.ok) {
        let detail = "请求失败";
        try {
          const err = await resp.json();
          detail = err.error || detail;
        } catch {}
        throw new Error(detail);
      }
      if (!resp.body) throw new Error("浏览器不支持流式读取");

      await parseEventStream(resp.body.getReader(), (evt) => {
        if (evt.type === "search_start") {
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            search: { state: "loading", query: evt.query || "", results: [], error: "" }
          }));
          return;
        }
        if (evt.type === "search_done") {
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            search: {
              state: "done",
              query: msg.search.query,
              results: Array.isArray(evt.results) ? evt.results : [],
              error: ""
            }
          }));
          return;
        }
        if (evt.type === "search_error") {
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            search: { state: "error", query: msg.search.query, results: [], error: evt.error || "" }
          }));
          return;
        }
        if (evt.type === "context_usage") {
          const usage = evt.usage || {};
          const phase = usage.phase || "unknown";
          const used = Number(usage.used_estimated_tokens || 0);
          const total = Number(usage.window_total_tokens || 0);
          const ratio = Number(usage.usage_ratio || 0);
          const pct = (ratio * 100).toFixed(2);
          const mn = usage.model ? ` - ${usage.model}` : "";
          const line = `[${phase}] ${used}/${total} tokens (${pct}%)${mn}`;
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            usageLines: [...msg.usageLines, line]
          }));
          return;
        }
        if (evt.type === "reasoning") {
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            reasoning: `${msg.reasoning}${evt.content || ""}`
          }));
          return;
        }
        if (evt.type === "token") {
          answer += evt.content || "";
          updateStreamMessage(streamId, (msg) => ({
            ...msg,
            answer: answer || "正在思考..."
          }));
          return;
        }
        if (evt.type === "error") {
          throw new Error(evt.error || "Streaming request failed");
        }
      });

      if (!answer) {
        answer = "(empty response)";
        updateStreamMessage(streamId, (msg) => ({ ...msg, answer }));
      }

      setHistory((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: answer }]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "请求失败";
      updateStreamMessage(streamId, (msg) => ({ ...msg, answer: `Error: ${message}` }));
    } finally {
      setPending(false);
    }
  }

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
            <p>支持 Web Search、Thinking 与流式 Reasoning 展示。</p>
          </div>
          <div className="header-meta">
            <span className="meta-pill">SSE Streaming</span>
            <span className="meta-pill">Math + Markdown</span>
            <span className="meta-pill">K2.5 / QWEN3.5 / GLM5</span>
          </div>
        </header>

        <div className="status-bar">
          <span className={`status-dot ${isPending ? "busy" : ""}`} />
          <span>{isPending ? "模型正在生成回答..." : "就绪"}</span>
        </div>

        <div id="messages" className="messages" ref={messagesRef} data-testid="messages-list">
          {messages.map((msg) => {
            if (msg.role === "assistant_stream") {
              return (
                <div key={msg.id} className="msg assistant stream">
                  {msg.search.state !== "hidden" && (
                    <CollapsibleSection title="Search" className="search" defaultOpen={true}>
                      <div data-testid="search-panel">
                      <div className="assistant-body">
                        {msg.search.state === "loading" && (
                          <span className="search-loading">正在搜索: &ldquo;{msg.search.query}&rdquo;...</span>
                        )}
                        {msg.search.state === "error" && (
                          <span className="search-error">搜索失败: {msg.search.error}</span>
                        )}
                        {msg.search.state === "done" && msg.search.results.length === 0 && (
                          <span className="search-empty">未找到相关结果</span>
                        )}
                        {msg.search.state === "done" && msg.search.results.length > 0 && (
                          <div className="search-results">
                            {msg.search.results.map((item, idx) => (
                              <div className="search-item" key={`${msg.id}-s-${idx}`}>
                                [{idx + 1}]{" "}
                                <a href={item.url} target="_blank" rel="noreferrer noopener">
                                  {item.title || item.url}
                                </a>
                                {item.snippet && <div className="search-snippet">{item.snippet}</div>}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                      </div>
                    </CollapsibleSection>
                  )}

                  {msg.usageLines.length > 0 && (
                    <CollapsibleSection title="Context Usage" className="usage" defaultOpen={false}>
                      <div data-testid="usage-panel">
                      <div className="assistant-body">
                        {msg.usageLines.map((line, idx) => (
                          <div className="agent-loading" key={`${msg.id}-u-${idx}`}>
                            {line}
                          </div>
                        ))}
                      </div>
                      </div>
                    </CollapsibleSection>
                  )}

                  {msg.reasoning && (
                    <CollapsibleSection title="Reasoning" className="reasoning" defaultOpen={true}>
                      <div data-testid="reasoning-panel">
                      <RichBlock className="assistant-body" text={msg.reasoning} />
                      </div>
                    </CollapsibleSection>
                  )}

                  <div className="assistant-section answer">
                    <div className="assistant-title">Answer</div>
                    <RichBlock className="assistant-body" text={msg.answer} />
                    {isPending && (
                      <span className="typing-dots" aria-label="正在输入">
                        <span className="dot" />
                        <span className="dot" />
                        <span className="dot" />
                      </span>
                    )}
                  </div>
                </div>
              );
            }

            return msg.role === "assistant" ? (
              <div key={msg.id} className="msg assistant">
                <RichBlock className="assistant-body" text={msg.content} />
              </div>
            ) : (
              <div key={msg.id} className="msg user">
                {msg.content}
              </div>
            );
          })}
        </div>

        <form className="composer" onSubmit={onSubmit}>
          <div className="settings-card">
            <div className="model-field">
              <span className="model-field-label">模型</span>
              <ModelSelect
                models={MODELS}
                value={model}
                disabled={isPending}
                onChange={setModel}
              />
            </div>

            <div className="toggles" role="group" aria-label="chat options">
              <label className="toggle" htmlFor="searchToggle">
                <input
                  type="checkbox"
                  id="searchToggle"
                  checked={webSearch}
                  disabled={isPending}
                  onChange={(event) => setWebSearch(event.target.checked)}
                />
                <span className="toggle-track" aria-hidden="true" />
                <span className="toggle-label">网页搜索</span>
              </label>

              {supportsThinking && (
                <label className="toggle" htmlFor="thinkingToggle">
                  <input
                    type="checkbox"
                    id="thinkingToggle"
                    checked={thinkingMode}
                    disabled={isPending}
                    onChange={(event) => setThinkingMode(event.target.checked)}
                  />
                  <span className="toggle-track" aria-hidden="true" />
                  <span className="toggle-label">Thinking 模式</span>
                </label>
              )}
            </div>
          </div>

          <div className="input-shell">
            {/* Attachment strip */}
            {supportsMedia && (attachments.length > 0 || true) && (
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
                      onClick={() => removeAttachment(att.id)}
                      aria-label={`删除 ${att.name}`}
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
                    title="添加图片或视频"
                    aria-label="添加文件"
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
                  onChange={(event) => handleFilesSelected(event.target.files)}
                />
              </div>
            )}

            <div className="input-row">
              <textarea
                id="input"
                value={input}
                disabled={isPending}
                placeholder="输入内容后按 Enter 发送（Shift+Enter 换行）"
                required
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <button id="sendBtn" type="submit" disabled={isPending} aria-label="发送">
                <svg className="send-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 2L11 13" />
                  <path d="M22 2L15 22L11 13L2 9L22 2Z" />
                </svg>
              </button>
            </div>
          </div>
        </form>

        <div className="tip">
          三个模型最大生成 token 固定为 16384；k2.5、qwen3.5 与 glm5 均支持 Thinking/Instant，图片/视频输入仅 k2.5。
        </div>
      </div>
    </div>
  );
}
