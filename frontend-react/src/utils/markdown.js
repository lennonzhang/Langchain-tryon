import DOMPurify from "dompurify";
import { marked } from "marked";

// Custom renderer: wrap fenced code blocks with Mac-style chrome bar
const renderer = new marked.Renderer();

renderer.code = function (code, lang /*, escaped */) {
  const rawLanguage = (lang || "").split(/\s+/)[0];
  const language = rawLanguage.toLowerCase().replace(/[^a-z0-9_-]/g, "") || "text";
  const displayLang = language;
  const escaped = String(code)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

  return `<div class="code-block-wrapper">
  <div class="code-block-chrome">
    <span class="code-dots"><i></i><i></i><i></i></span>
    <span class="code-lang">${displayLang}</span>
    <button class="code-copy-btn" type="button">Copy</button>
  </div>
  <pre><code class="language-${language}">${escaped}\n</code></pre>
</div>`;
};

export function toSafeHtml(source) {
  const text = typeof source === "string" ? source : String(source ?? "");
  const parsed = marked.parse(text, {
    gfm: true,
    breaks: true,
    renderer,
  });
  return DOMPurify.sanitize(parsed, { USE_PROFILES: { html: true } });
}
