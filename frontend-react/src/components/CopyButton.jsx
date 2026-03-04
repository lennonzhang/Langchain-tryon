import { useState, useCallback, useRef, useEffect } from "react";

export default function CopyButton({ text, className = "" }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);

  // Cleanup timer on unmount
  useEffect(() => () => clearTimeout(timerRef.current), []);

  const handleCopy = useCallback(async () => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API not available — silent fail
    }
  }, [text]);

  const cls = ["copy-btn", copied && "copied", className].filter(Boolean).join(" ");

  return (
    <button
      type="button"
      className={cls}
      onClick={handleCopy}
      aria-label={copied ? "Copied" : "Copy to clipboard"}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}
