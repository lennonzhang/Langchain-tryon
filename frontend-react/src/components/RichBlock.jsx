import { useEffect, useMemo, useRef, useState } from "react";
import { toPlainHtml, toSafeHtml, ensureMarkdownLoaded, isMarkdownReady } from "../utils/markdown";
import { ensurePrismLoaded } from "../utils/prism-loader";

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
  const [ready, setReady] = useState(isMarkdownReady);
  useEffect(() => {
    if (ready) return undefined;
    let cancelled = false;

    ensureMarkdownLoaded()
      .then(() => {
        if (!cancelled) setReady(true);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [ready]);

  const html = useMemo(() => (ready ? toSafeHtml(text) : toPlainHtml(text)), [text, ready]);
  const containerRef = useRef(null);
  const copyResetTimersRef = useRef(new WeakMap());
  const copyResetTimerIdsRef = useRef(new Set());

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

  // Code block copy: single delegated listener to avoid per-button churn.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleClick = async (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;

      const btn = target.closest(".code-copy-btn");
      if (!btn) return;

      const wrapper = btn.closest(".code-block-wrapper");
      const codeEl = wrapper?.querySelector("code");
      if (!codeEl) return;

      const previousTimerId = copyResetTimersRef.current.get(btn);
      if (previousTimerId) {
        clearTimeout(previousTimerId);
        copyResetTimerIdsRef.current.delete(previousTimerId);
      }

      try {
        await navigator.clipboard.writeText(codeEl.textContent || "");
        btn.textContent = "Copied!";
        btn.classList.add("copied");
        const timerId = setTimeout(() => {
          btn.textContent = "Copy";
          btn.classList.remove("copied");
          copyResetTimerIdsRef.current.delete(timerId);
          copyResetTimersRef.current.delete(btn);
        }, 2000);
        copyResetTimersRef.current.set(btn, timerId);
        copyResetTimerIdsRef.current.add(timerId);
      } catch {
        /* clipboard not available */
      }
    };

    container.addEventListener("click", handleClick);

    return () => {
      container.removeEventListener("click", handleClick);
      copyResetTimerIdsRef.current.forEach((timerId) => clearTimeout(timerId));
      copyResetTimerIdsRef.current.clear();
      copyResetTimersRef.current = new WeakMap();
    };
  }, []);

  // Prism highlighting: skip while streaming, run once after completion.
  useEffect(() => {
    if (streaming) return;
    const container = containerRef.current;
    if (!container) return;

    const codeNodes = container.querySelectorAll('pre code[class*="language-"]');
    if (codeNodes.length === 0) return;

    let cancelled = false;

    const highlightPendingCodeBlocks = () => {
      if (cancelled || !window.Prism) return;
      container
        .querySelectorAll('pre code[class*="language-"]')
        .forEach((node) => {
          if (node.dataset.prismHighlighted === "1") return;
          window.Prism.highlightElement(node);
          node.dataset.prismHighlighted = "1";
        });
    };

    if (window.Prism) {
      highlightPendingCodeBlocks();
    } else {
      ensurePrismLoaded()
        .then(() => {
          highlightPendingCodeBlocks();
        })
        .catch(() => {});
    }

    return () => {
      cancelled = true;
    };
  }, [html, streaming]);

  return <div ref={containerRef} className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}
