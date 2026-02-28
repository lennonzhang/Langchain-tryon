import DOMPurify from "dompurify";
import { marked } from "marked";

export function toSafeHtml(source) {
  const text = typeof source === "string" ? source : String(source ?? "");
  const parsed = marked.parse(text, {
    gfm: true,
    breaks: true,
    mangle: false,
    headerIds: false,
  });
  return DOMPurify.sanitize(parsed, { USE_PROFILES: { html: true } });
}
