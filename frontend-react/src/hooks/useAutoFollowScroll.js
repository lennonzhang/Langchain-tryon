import { useCallback, useEffect, useRef } from "react";

export function useAutoFollowScroll({ thresholdPx = 150, watchValue }) {
  const containerRef = useRef(null);
  const stickToBottomRef = useRef(true);
  const previousScrollHeightRef = useRef(0);
  const rafRef = useRef(null);
  const mutationObserverRef = useRef(null);

  const getDistanceToBottom = useCallback((el) => {
    return el.scrollHeight - el.scrollTop - el.clientHeight;
  }, []);

  const syncScrollPosition = useCallback(() => {
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
      el.scrollTop = el.scrollHeight;
    }

    previousScrollHeightRef.current = el.scrollHeight;
  }, [getDistanceToBottom, thresholdPx]);

  const scheduleSyncScrollPosition = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
    }

    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      syncScrollPosition();
    });
  }, [syncScrollPosition]);

  const handleScroll = useCallback((event) => {
    const el = event?.currentTarget || containerRef.current;
    if (!el) return;
    const distanceToBottom = getDistanceToBottom(el);
    stickToBottomRef.current = distanceToBottom <= thresholdPx;
    previousScrollHeightRef.current = el.scrollHeight;
  }, [getDistanceToBottom, thresholdPx]);

  useEffect(() => {
    // Cancel any pending frame and reschedule (batches rapid updates to one per frame)
    scheduleSyncScrollPosition();
  }, [scheduleSyncScrollPosition, watchValue]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof MutationObserver === "undefined") return undefined;

    const observer = new MutationObserver(() => {
      if (!stickToBottomRef.current) return;
      scheduleSyncScrollPosition();
    });

    observer.observe(el, {
      childList: true,
      characterData: true,
      subtree: true,
    });

    mutationObserverRef.current = observer;

    return () => {
      observer.disconnect();
      if (mutationObserverRef.current === observer) {
        mutationObserverRef.current = null;
      }
    };
  }, [scheduleSyncScrollPosition]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (mutationObserverRef.current) mutationObserverRef.current.disconnect();
    };
  }, []);

  return {
    containerRef,
    handleScroll,
  };
}
