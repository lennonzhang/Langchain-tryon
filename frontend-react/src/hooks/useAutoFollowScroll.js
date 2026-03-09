import { useCallback, useEffect, useRef } from "react";

export function useAutoFollowScroll({ thresholdPx = 150, watchValue }) {
  const containerRef = useRef(null);
  const stickToBottomRef = useRef(true);
  const previousScrollHeightRef = useRef(0);

  const getDistanceToBottom = useCallback((el) => {
    return el.scrollHeight - el.scrollTop - el.clientHeight;
  }, []);

  const handleScroll = useCallback((event) => {
    const el = event?.currentTarget || containerRef.current;
    if (!el) return;
    const distanceToBottom = getDistanceToBottom(el);
    stickToBottomRef.current = distanceToBottom <= thresholdPx;
    previousScrollHeightRef.current = el.scrollHeight;
  }, [getDistanceToBottom, thresholdPx]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const distanceToBottom = getDistanceToBottom(el);
    const previousScrollHeight = previousScrollHeightRef.current;
    const previousDistanceToBottom =
      previousScrollHeight > 0 ? previousScrollHeight - el.scrollTop - el.clientHeight : 0;

    if (distanceToBottom <= thresholdPx || previousDistanceToBottom <= thresholdPx) {
      stickToBottomRef.current = true;
    }

    if (stickToBottomRef.current) {
      requestAnimationFrame(() => {
        const currentEl = containerRef.current;
        if (!currentEl) return;
        currentEl.scrollTop = currentEl.scrollHeight;
      });
    }

    previousScrollHeightRef.current = el.scrollHeight;
  }, [getDistanceToBottom, thresholdPx, watchValue]);

  return {
    containerRef,
    handleScroll,
  };
}
