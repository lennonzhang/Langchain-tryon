import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@tanstack/react-query": resolve(__dirname, "src/shared/vendor/react-query.js"),
      zustand: resolve(__dirname, "src/shared/vendor/zustand.js"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./vitest.setup.js",
    css: true,
    exclude: ["tests/**", "node_modules/**"],
  },
});
