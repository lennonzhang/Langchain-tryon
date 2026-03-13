import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

export const CRITICAL_SHELL_CSS_PATH = resolve(__dirname, "styles", "critical-shell.css");

export function loadCriticalShellCss() {
  return readFileSync(CRITICAL_SHELL_CSS_PATH, "utf8").trim();
}

export function injectCriticalShellCss(html, css = loadCriticalShellCss()) {
  return html.replace("</head>", `<style data-critical-shell="true">${css}</style>\n</head>`);
}
