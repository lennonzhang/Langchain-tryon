import { describe, expect, it } from "vitest";
import { buildMessagePreview, buildSessionTitle } from "../entities/session/sessionSummary";

describe("sessionSummary", () => {
  it("builds title with cleanup and truncation", () => {
    expect(buildSessionTitle("   ")).toBe("New Chat");
    expect(buildSessionTitle("## Hello   world")).toBe("Hello world");
    expect(buildSessionTitle("this is a very long line that should be truncated by title builder"))
      .toBe("this is a very long line that ...");
  });

  it("builds message preview", () => {
    expect(buildMessagePreview("\n\n")).toBe("");
    expect(buildMessagePreview("a\n b\n c")).toBe("a b c");
    expect(buildMessagePreview("x".repeat(81))).toBe(`${"x".repeat(80)}...`);
  });
});
