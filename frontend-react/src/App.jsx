import { useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { parseEventStream } from "./stream";

const MODELS = ["moonshotai/kimi-k2.5", "z-ai/glm4.7"];
const CONNECTED_TEXT = "已连接，输入你的问题开始对话。";

function modelSupportsThinking(model) {
  return model.startsWith("moonshotai/") || model.startsWith("z-ai/");
}

function modelSupportsImageInput(model) {
  return model.startsWith("moonshotai/");
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

function RichBlock({ text, className }) {
  const html = useMemo(() => toSafeHtml(text), [text]);

  useEffect(() => {
    if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
      window.MathJax.typesetPromise().catch(() => {
        // Keep markdown visible even if math rendering fails.
      });
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

async function readFilesAsDataUrls(fileList) {
  const files = Array.from(fileList || []).slice(0, 3);
  const tasks = files.map(
    (file) =>
      new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
        reader.onerror = () => reject(new Error(`Failed to read image: ${file.name}`));
        reader.readAsDataURL(file);
      })
  );
  const result = await Promise.all(tasks);
  return result.filter(Boolean);
}

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
  const [imageCount, setImageCount] = useState(0);

  const supportsThinking = modelSupportsThinking(model);
  const supportsImageInput = modelSupportsImageInput(model);

  useEffect(() => {
    if (!supportsImageInput && fileInputRef.current) {
      fileInputRef.current.value = "";
      setImageCount(0);
    }
  }, [supportsImageInput]);

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
        if (msg.id !== streamId || msg.role !== "assistant_stream") {
          return msg;
        }
        return updater(msg);
      })
    );
  }

  async function onSubmit(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || isPending) {
      return;
    }

    const effectiveThinking = supportsThinking ? thinkingMode : true;
    const images = supportsImageInput ? await readFilesAsDataUrls(fileInputRef.current?.files) : [];
    const tags = [model];
    if (webSearch) {
      tags.push("Search");
    }
    if (supportsThinking) {
      tags.push(effectiveThinking ? "Thinking" : "Instant");
    }
    if (supportsImageInput && images.length > 0) {
      tags.push(`Img x${images.length}`);
    }

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
          images
        })
      });

      if (!resp.ok) {
        let detail = "请求失败";
        try {
          const err = await resp.json();
          detail = err.error || detail;
        } catch {
          // Keep fallback message when server doesn't return JSON.
        }
        throw new Error(detail);
      }
      if (!resp.body) {
        throw new Error("浏览器不支持流式读取");
      }

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
            search: {
              state: "error",
              query: msg.search.query,
              results: [],
              error: evt.error || ""
            }
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
          const modelName = usage.model ? ` - ${usage.model}` : "";
          const line = `[${phase}] ${used}/${total} tokens (${pct}%)${modelName}`;
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
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setImageCount(0);
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
            <span className="meta-pill">K2.5 / GLM4.7</span>
          </div>
        </header>

        <div className="status-bar">
          <span className={`status-dot ${isPending ? "busy" : ""}`} />
          <span>{isPending ? "模型正在生成回答..." : "就绪"}</span>
        </div>

        <div id="messages" className="messages" ref={messagesRef}>
          {messages.map((msg) => {
            if (msg.role === "assistant_stream") {
              return (
                <div key={msg.id} className="msg assistant stream">
                  {msg.search.state !== "hidden" && (
                    <CollapsibleSection title="Search" className="search" defaultOpen={true}>
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
                    </CollapsibleSection>
                  )}

                  {msg.usageLines.length > 0 && (
                    <CollapsibleSection title="Context Usage" className="usage" defaultOpen={false}>
                      <div className="assistant-body">
                        {msg.usageLines.map((line, idx) => (
                          <div className="agent-loading" key={`${msg.id}-u-${idx}`}>
                            {line}
                          </div>
                        ))}
                      </div>
                    </CollapsibleSection>
                  )}

                  {msg.reasoning && (
                    <CollapsibleSection title="Reasoning" className="reasoning" defaultOpen={true}>
                      <RichBlock className="assistant-body" text={msg.reasoning} />
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
            <label className="model-field" htmlFor="modelSelect">
              模型
              <select
                id="modelSelect"
                value={model}
                disabled={isPending}
                onChange={(event) => setModel(event.target.value)}
              >
                {MODELS.map((item) => (
                  <option value={item} key={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>

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

          <div className="compose-row">
            <div className={`input-shell ${supportsImageInput ? "" : "no-image"}`.trim()}>
              {supportsImageInput && (
                <button
                  type="button"
                  className="image-picker-btn"
                  disabled={isPending}
                  title="添加图片（仅 k2.5）"
                  aria-label="添加图片"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <span>+</span>
                  {imageCount > 0 && <em className="image-count-badge">{Math.min(imageCount, 3)}</em>}
                </button>
              )}

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

              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                hidden
                disabled={isPending}
                onChange={(event) => setImageCount(event.target.files?.length || 0)}
              />
            </div>

            <button id="sendBtn" type="submit" disabled={isPending}>
              <span className="send-label">发送</span>
              <svg className="send-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2L11 13" />
                <path d="M22 2L15 22L11 13L2 9L22 2Z" />
              </svg>
            </button>
          </div>
        </form>

        <div className="tip">
          两个模型最大生成 token 固定为 16384；k2.5 与 glm4.7 均支持 Thinking/Instant，图片输入仅 k2.5。
        </div>
      </div>
    </div>
  );
}
