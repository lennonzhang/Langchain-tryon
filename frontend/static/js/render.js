export function renderRichText(target, source) {
  const text = typeof source === "string" ? source : String(source ?? "");

  let html;
  if (window.marked && typeof window.marked.parse === "function") {
    html = window.marked.parse(text, {
      gfm: true,
      breaks: true,
      mangle: false,
      headerIds: false,
    });
  } else {
    html = escapeHtml(text).replace(/\n/g, "<br>");
  }

  if (window.DOMPurify && typeof window.DOMPurify.sanitize === "function") {
    html = window.DOMPurify.sanitize(html, {
      USE_PROFILES: { html: true },
    });
  }

  target.innerHTML = html;

  if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
    window.MathJax.typesetPromise([target]).catch(() => {
      // Ignore formula render failures and keep markdown content visible.
    });
  }
}

function escapeHtml(input) {
  return input
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}