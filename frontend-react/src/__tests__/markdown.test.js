import { describe, expect, it } from "vitest";
import { toSafeHtml } from "../utils/markdown";

describe("toSafeHtml code rendering", () => {
  it("wraps fenced code with chrome wrapper and copy button", () => {
    const html = toSafeHtml("```js\nconsole.log('hi')\n```");

    expect(html).toContain('class="code-block-wrapper"');
    expect(html).toContain('class="code-block-chrome"');
    expect(html).toContain('class="code-lang"');
    expect(html).toContain(">js<");
    expect(html).toContain('class="code-copy-btn"');
  });

  it("uses text as default language when missing", () => {
    const html = toSafeHtml("```\nhello\n```");
    expect(html).toContain(">text<");
    expect(html).toContain('class="language-text"');
  });

  it("normalizes language info string and strips dangerous chars", () => {
    const html = toSafeHtml("```<script>alert(1)</script>\ncode\n```");
    expect(html).not.toContain("<script>");
    expect(html).toContain(">scriptalert1script<");
    expect(html).toContain('class="language-scriptalert1script"');
  });

  it("keeps inline code without fenced wrapper", () => {
    const html = toSafeHtml("Use `npm install` here.");
    expect(html).toContain("<code>npm install</code>");
    expect(html).not.toContain("code-block-wrapper");
  });
});
