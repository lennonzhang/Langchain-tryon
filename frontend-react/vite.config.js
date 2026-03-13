import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { injectCriticalShellCss } from "./src/criticalCss.js";

function inlineCriticalCss() {
  return {
    name: "inline-critical-css",
    enforce: "post",
    transformIndexHtml(html) {
      return injectCriticalShellCss(html);
    },
  };
}

export default defineConfig({
  plugins: [react(), inlineCriticalCss()],
  resolve: {
    alias: {
      "@tanstack/react-query": resolve(__dirname, "src/shared/vendor/react-query.js"),
      zustand: resolve(__dirname, "src/shared/vendor/zustand.js"),
    },
  },
  build: {
    outDir: "../frontend/dist",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom"],
          "vendor-markdown": ["marked", "dompurify"],
        },
      },
    },
  },
});
