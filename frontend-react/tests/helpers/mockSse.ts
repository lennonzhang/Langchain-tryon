import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Page } from "@playwright/test";

export async function mockSseFromFixture(page: Page, fixtureName: string) {
  const here = dirname(fileURLToPath(import.meta.url));
  const fixturePath = resolve(here, "..", "fixtures", "sse", fixtureName);
  const body = readFileSync(fixturePath, "utf8");
  await page.route("**/api/chat/stream", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
      headers: {
        "cache-control": "no-cache",
        connection: "keep-alive",
      },
    });
  });
}

export async function mockDelayedSseFromFixture(
  page: Page,
  fixtureName: string,
  delayMs: number
) {
  const here = dirname(fileURLToPath(import.meta.url));
  const fixturePath = resolve(here, "..", "fixtures", "sse", fixtureName);
  const body = readFileSync(fixturePath, "utf8");
  await page.route("**/api/chat/stream", async (route) => {
    await new Promise((resolveDelay) => setTimeout(resolveDelay, delayMs));
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
      headers: {
        "cache-control": "no-cache",
        connection: "keep-alive",
      },
    });
  });
}

export async function sendMessage(page: Page, text: string) {
  const textarea = page.locator("textarea");
  await textarea.fill(text);
  await textarea.press("Enter");
}

export async function stabilizeForScreenshot(page: Page) {
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation: none !important;
        transition: none !important;
        caret-color: transparent !important;
      }
    `,
  });
}
