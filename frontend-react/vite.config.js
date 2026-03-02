import { defineConfig } from "vite";
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
  build: {
    outDir: "../frontend/dist",
    emptyOutDir: true
  }
});
