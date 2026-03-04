import { useEffect, useMemo, useRef } from "react";
import { toSafeHtml } from "../utils/markdown";

const MATHJAX_DEBOUNCE_MS = 500;

/**
 * Renders markdown text as sanitized HTML.
 *
 * The `streaming` prop signals that text is being built incrementally.
 * When streaming, MathJax typesetting is debounced (500ms) to avoid
 * expensive re-typeset on every token. Completed messages typeset immediately.
 * MathJax is scoped to this component's container to avoid O(N) full-page scans.
 */
export default function RichBlock({ text, className, streaming = false }) {
  const html = useMemo(() => toSafeHtml(text), [text]);
  const containerRef = useRef(null);

  // Debounce MathJax typesetting — immediate for completed, delayed for streaming
  const mathJaxTimerRef = useRef(null);
  useEffect(() => {
    if (!html) return;
    if (!window.MathJax || typeof window.MathJax.typesetPromise !== "function") return;

    if (mathJaxTimerRef.current !== null) {
      clearTimeout(mathJaxTimerRef.current);
    }

    const delay = streaming ? MATHJAX_DEBOUNCE_MS : 0;
    const target = containerRef.current ? [containerRef.current] : undefined;

    mathJaxTimerRef.current = setTimeout(() => {
      mathJaxTimerRef.current = null;
      window.MathJax.typesetPromise(target).catch(() => {});
    }, delay);

    return () => {
      if (mathJaxTimerRef.current !== null) {
        clearTimeout(mathJaxTimerRef.current);
        mathJaxTimerRef.current = null;
      }
    };
  }, [html, streaming]);

  return <div ref={containerRef} className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}
