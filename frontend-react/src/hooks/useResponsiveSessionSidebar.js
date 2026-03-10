import { useCallback, useLayoutEffect, useRef, useState } from "react";

const MOBILE_MEDIA_QUERY = "(max-width: 600px)";
const SESSION_OVERLAY_RATIO = 2.7;

function isMobileViewport() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }

  return window.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

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
  const [isSessionOverlay, setIsSessionOverlay] = useState(() => isMobileViewport());

  const syncLayoutMode = useCallback(() => {
    const viewportMobile = isMobileViewport();
    if (viewportMobile) {
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
    const handleViewportChange = () => syncLayoutMode();

    if (mediaQueryList) {
      if (typeof mediaQueryList.addEventListener === "function") {
        mediaQueryList.addEventListener("change", handleViewportChange);
      } else if (typeof mediaQueryList.addListener === "function") {
        mediaQueryList.addListener(handleViewportChange);
      }
    }

    window.addEventListener("resize", handleViewportChange);

    let resizeObserver = null;
    if (typeof ResizeObserver === "function") {
      resizeObserver = new ResizeObserver(() => syncLayoutMode());
      if (appShellRef.current) {
        resizeObserver.observe(appShellRef.current);
      }
      if (sidebarRef.current) {
        resizeObserver.observe(sidebarRef.current);
      }
    }

    return () => {
      if (mediaQueryList) {
        if (typeof mediaQueryList.removeEventListener === "function") {
          mediaQueryList.removeEventListener("change", handleViewportChange);
        } else if (typeof mediaQueryList.removeListener === "function") {
          mediaQueryList.removeListener(handleViewportChange);
        }
      }

      window.removeEventListener("resize", handleViewportChange);
      resizeObserver?.disconnect();
    };
  }, [syncLayoutMode]);

  return {
    appShellRef,
    sidebarRef,
    isSessionOverlay,
  };
}
