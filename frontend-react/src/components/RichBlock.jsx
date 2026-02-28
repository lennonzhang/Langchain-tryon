import { useEffect, useMemo } from "react";
import { toSafeHtml } from "../utils/markdown";

export default function RichBlock({ text, className }) {
  const html = useMemo(() => toSafeHtml(text), [text]);

  useEffect(() => {
    if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
      window.MathJax.typesetPromise().catch(() => {});
    }
  }, [html]);

  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}
