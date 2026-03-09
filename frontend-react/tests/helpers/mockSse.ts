import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Page } from "@playwright/test";

const CHAT_STREAM_PATH = "/api/chat/stream";

function loadFixtureBody(fixtureName: string) {
  const here = dirname(fileURLToPath(import.meta.url));
  const fixturePath = resolve(here, "..", "fixtures", "sse", fixtureName);
  return readFileSync(fixturePath, "utf8").replace(/\r\n/g, "\n");
}

export async function mockSseFromFixture(page: Page, fixtureName: string) {
  const body = loadFixtureBody(fixtureName);
  await page.route(`**${CHAT_STREAM_PATH}*`, async (route) => {
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
  const body = loadFixtureBody(fixtureName);
  await page.route(`**${CHAT_STREAM_PATH}*`, async (route) => {
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

export async function mockChunkedSseFromFixture(
  page: Page,
  fixtureName: string,
  delayMs = 60
) {
  const body = loadFixtureBody(fixtureName);
  await page.addInitScript(
    ({ fixtureBody, chunkDelayMs, streamPath }) => {
      const originalFetch = window.fetch.bind(window);
      const normalizedBody = fixtureBody.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      const chunks = normalizedBody
        .split("\n\n")
        .map((block) => block.trim())
        .filter(Boolean)
        .map((block) => `${block}\n\n`);

      window.fetch = async (input, init) => {
        const requestUrl =
          typeof input === "string" || input instanceof URL ? String(input) : input.url;
        const pathname = new URL(requestUrl, window.location.href).pathname;
        if (pathname !== streamPath) {
          return originalFetch(input, init);
        }

        const encoder = new TextEncoder();
        const signal =
          init?.signal || (typeof Request !== "undefined" && input instanceof Request ? input.signal : undefined);

        const stream = new ReadableStream({
          async start(controller) {
            const abortError = () => signal?.reason ?? new DOMException("Aborted", "AbortError");
            const handleAbort = () => controller.error(abortError());
            signal?.addEventListener("abort", handleAbort, { once: true });

            try {
              for (let index = 0; index < chunks.length; index += 1) {
                if (signal?.aborted) {
                  throw abortError();
                }
                controller.enqueue(encoder.encode(chunks[index]));
                if (index < chunks.length - 1) {
                  await new Promise((resolveDelay) => window.setTimeout(resolveDelay, chunkDelayMs));
                }
              }
              controller.close();
            } catch (error) {
              controller.error(error);
            } finally {
              signal?.removeEventListener("abort", handleAbort);
            }
          },
        });

        return new Response(stream, {
          status: 200,
          headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
          },
        });
      };
    },
    { fixtureBody: body, chunkDelayMs: delayMs, streamPath: CHAT_STREAM_PATH },
  );
}

export async function sendMessage(page: Page, text: string) {
  const textarea = page.locator("textarea");
  await textarea.fill(text);
  await page.locator("#sendBtn").click();
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
