import { describe, expect, it } from "vitest";
import { injectCriticalShellCss, loadCriticalShellCss } from "../criticalCss";

describe("critical shell css", () => {
  it("loads the shared critical shell stylesheet", () => {
    const css = loadCriticalShellCss();

    expect(css).toContain(".app-shell");
    expect(css).toContain(".chat");
    expect(css).toContain(".messages");
  });

  it("injects inline critical shell css into index html", () => {
    const html = injectCriticalShellCss("<html><head></head><body></body></html>");

    expect(html).toContain('style data-critical-shell="true"');
    expect(html).toContain(".app-shell");
    expect(html).toContain(".chat");
  });
});
