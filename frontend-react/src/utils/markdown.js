// Lazy-loaded singletons (same pattern as prism-loader.js)
let _marked = null;
let _DOMPurify = null;
let _renderer = null;
let _loadPromise = null;
let _warmupScheduled = false;
let _moduleLoader = defaultModuleLoader;

function escapeHtml(source) {
  return String(source ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function resolveDOMPurify(moduleValue) {
  const candidate = moduleValue?.default ?? moduleValue;
  if (typeof candidate?.sanitize === "function") return candidate;
  if (typeof candidate?.default?.sanitize === "function") return candidate.default;
  throw new TypeError("DOMPurify module did not expose sanitize()");
}

async function defaultModuleLoader() {
  const [markedModule, domPurifyModule] = await Promise.all([
    import("marked").then((m) => m.marked),
    import("dompurify"),
  ]);
  return {
    marked: markedModule,
    DOMPurify: resolveDOMPurify(domPurifyModule),
  };
}

function buildRenderer(markedLib) {
  const renderer = new markedLib.Renderer();
  renderer.code = function (code, lang) {
    const rawLanguage = (lang || "").split(/\s+/)[0];
    const language = rawLanguage.toLowerCase().replace(/[^a-z0-9_-]/g, "") || "text";
    const escaped = escapeHtml(code);
    return `<div class="code-block-wrapper">
  <div class="code-block-chrome">
    <span class="code-dots"><i></i><i></i><i></i></span>
    <span class="code-lang">${language}</span>
    <button class="code-copy-btn" type="button">Copy</button>
  </div>
  <pre><code class="language-${language}">${escaped}\n</code></pre>
</div>`;
  };
  return renderer;
}

export function ensureMarkdownLoaded() {
  if (_marked && _DOMPurify) return Promise.resolve();
  if (!_loadPromise) {
    _loadPromise = _moduleLoader().then(({ marked, DOMPurify }) => {
      _marked = marked;
      _DOMPurify = DOMPurify;
      _renderer = buildRenderer(marked);
    }).catch((err) => {
      _loadPromise = null;
      throw err;
    });
  }
  return _loadPromise;
}

export function isMarkdownReady() {
  return Boolean(_marked && _DOMPurify);
}

export function scheduleMarkdownWarmup() {
  if (_warmupScheduled || typeof window === "undefined") return;
  _warmupScheduled = true;

  const warmup = () => {
    ensureMarkdownLoaded().catch(() => {});
  };
  const scheduleIdle = () => {
    if (typeof window.requestIdleCallback === "function") {
      window.requestIdleCallback(warmup, { timeout: 1500 });
      return;
    }
    window.setTimeout(warmup, 0);
  };

  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(() => scheduleIdle());
    return;
  }
  window.setTimeout(scheduleIdle, 0);
}

export function toPlainHtml(source) {
  const text = typeof source === "string" ? source : String(source ?? "");
  return escapeHtml(text).replace(/\r?\n/g, "<br />");
}

export function toSafeHtml(source) {
  if (!_marked || !_DOMPurify) return "";
  const text = typeof source === "string" ? source : String(source ?? "");
  const parsed = _marked.parse(text, {
    gfm: true,
    breaks: true,
    renderer: _renderer,
  });
  return _DOMPurify.sanitize(parsed, { USE_PROFILES: { html: true } });
}

export function __resetMarkdownStateForTests() {
  _marked = null;
  _DOMPurify = null;
  _renderer = null;
  _loadPromise = null;
  _warmupScheduled = false;
  _moduleLoader = defaultModuleLoader;
}

export function __setMarkdownLoaderForTests(loader) {
  _marked = null;
  _DOMPurify = null;
  _renderer = null;
  _loadPromise = null;
  _moduleLoader = async () => {
    const result = await loader();
    if (Array.isArray(result)) {
      const [marked, DOMPurify] = result;
      return { marked, DOMPurify };
    }
    return result;
  };
}
