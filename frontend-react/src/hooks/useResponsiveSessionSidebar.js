import { useCallback, useLayoutEffect, useRef, useState } from "react";

const MOBILE_MEDIA_QUERY = "(max-width: 600px)";
const SESSION_OVERLAY_RATIO = 2.7;

function getElementWidth(element) {
  if (!element) return 0;
  const rectWidth = element.getBoundingClientRect?.().width;
  if (typeof rectWidth === "number" && rectWidth > 0) {
    return rectWidth;
  }
  return element.offsetWidth || 0;
}

export function useResponsiveSessionSidebar() {
  const appShellRef = useRef(null);
  const sidebarRef = useRef(null);
  const isMobileRef = useRef(false);
  const [isSessionOverlay, setIsSessionOverlay] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    const mobile = window.matchMedia(MOBILE_MEDIA_QUERY).matches;
    isMobileRef.current = mobile;
    return mobile;
  });

  const syncLayoutMode = useCallback(() => {
    if (isMobileRef.current) {
      setIsSessionOverlay(true);
      return;
    }

    const appShellWidth = getElementWidth(appShellRef.current);
    const sidebarWidth = getElementWidth(sidebarRef.current);

    if (!appShellWidth || !sidebarWidth) {
      setIsSessionOverlay(false);
      return;
    }

    setIsSessionOverlay(appShellWidth <= sidebarWidth * SESSION_OVERLAY_RATIO);
  }, []);

  useLayoutEffect(() => {
    syncLayoutMode();

    if (typeof window === "undefined") {
      return undefined;
    }

    const mediaQueryList =
      typeof window.matchMedia === "function" ? window.matchMedia(MOBILE_MEDIA_QUERY) : null;

    const handleMediaChange = (e) => {
      isMobileRef.current = e.matches;
      syncLayoutMode();
    };

    if (mediaQueryList) {
      if (typeof mediaQueryList.addEventListener === "function") {
        mediaQueryList.addEventListener("change", handleMediaChange);
      } else if (typeof mediaQueryList.addListener === "function") {
        mediaQueryList.addListener(handleMediaChange);
      }
    }

    let resizeObserver = null;
    const hasResizeObserver = typeof ResizeObserver === "function";

    if (hasResizeObserver) {
      resizeObserver = new ResizeObserver(() => syncLayoutMode());
      if (appShellRef.current) {
        resizeObserver.observe(appShellRef.current);
      }
      if (sidebarRef.current) {
        resizeObserver.observe(sidebarRef.current);
      }
    } else {
      window.addEventListener("resize", syncLayoutMode);
    }

    return () => {
      if (mediaQueryList) {
        if (typeof mediaQueryList.removeEventListener === "function") {
          mediaQueryList.removeEventListener("change", handleMediaChange);
        } else if (typeof mediaQueryList.removeListener === "function") {
          mediaQueryList.removeListener(handleMediaChange);
        }
      }

      if (hasResizeObserver) {
        resizeObserver?.disconnect();
      } else {
        window.removeEventListener("resize", syncLayoutMode);
      }
    };
  }, [syncLayoutMode]);

  return {
    appShellRef,
    sidebarRef,
    isSessionOverlay,
  };
}
