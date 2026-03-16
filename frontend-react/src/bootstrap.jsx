import React, { Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { scheduleMarkdownWarmup } from "./utils/markdown";
import "./styles.css";

export const Noop = () => null;

export function lazyOptional(loader, exportName) {
  return lazy(() =>
    loader()
      .then((module) => ({ default: module?.[exportName] ?? Noop }))
      .catch(() => ({ default: Noop })),
  );
}

export const Analytics = lazyOptional(() => import("@vercel/analytics/react"), "Analytics");
export const SpeedInsights = lazyOptional(() => import("@vercel/speed-insights/react"), "SpeedInsights");

export function AppBootstrap() {
  return (
    <React.StrictMode>
      <App />
      <Suspense fallback={null}>
        <Analytics />
        <SpeedInsights />
      </Suspense>
    </React.StrictMode>
  );
}

export function mountApp(rootElement = document.getElementById("root")) {
  if (!rootElement) {
    throw new Error("Missing #root element");
  }
  createRoot(rootElement).render(<AppBootstrap />);
  scheduleMarkdownWarmup();
}
