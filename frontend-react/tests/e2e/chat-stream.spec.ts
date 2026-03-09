import { expect, test } from "@playwright/test";
import { mockChunkedSseFromFixture, mockSseFromFixture, sendMessage } from "../helpers/mockSse";

async function getDistanceToBottom(page) {
  return page.locator("[data-testid='messages-list']").evaluate((el) => {
    return el.scrollHeight - el.scrollTop - el.clientHeight;
  });
}

async function waitForFollowState(page, expectedMaxDistance = 150) {
  await expect.poll(() => getDistanceToBottom(page)).toBeLessThanOrEqual(expectedMaxDistance);
}

async function waitForDistanceAbove(page, expectedMinDistance = 150) {
  await expect.poll(() => getDistanceToBottom(page)).toBeGreaterThan(expectedMinDistance);
}

async function scrollMessagesList(page, position: "top" | "bottom") {
  await page.locator("[data-testid='messages-list']").evaluate((el, target) => {
    const top = target === "top" ? 0 : el.scrollHeight;
    el.scrollTo({ top, behavior: "instant" });
    el.dispatchEvent(new UIEvent("scroll", { view: window }));
  }, position);
}

test.describe("chat stream e2e", () => {
  test("sends message and renders final answer", async ({ page }) => {
    await mockSseFromFixture(page, "stream-basic.txt");
    await page.goto("/");
    const messagesList = page.getByTestId("messages-list");
    await sendMessage(page, "hello");

    await expect(messagesList.getByText("Hello from SSE")).toBeVisible();
    await expect(messagesList.getByText(/\[single\] 120\/128000 tokens/)).toBeVisible();
  });

  test("renders search and reasoning sections", async ({ page }) => {
    await mockSseFromFixture(page, "stream-search-reasoning.txt");
    await page.goto("/");
    const messagesList = page.getByTestId("messages-list");

    await page.locator("#searchToggle").check({ force: true });
    await sendMessage(page, "find docs");

    await expect(page.getByTestId("search-panel")).toBeVisible();
    await expect(page.getByTestId("reasoning-panel")).toBeVisible();
    await expect(messagesList.getByText("Final answer from agent mode.")).toBeVisible();
  });

  test("switching kimi to qwen hides media strip", async ({ page }) => {
    await page.goto("/");

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles([
      {
        name: "sample.png",
        mimeType: "image/png",
        buffer: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wf8f7IAAAAASUVORK5CYII=",
          "base64"
        ),
      },
    ]);
    await expect(page.locator(".attach-thumb")).toHaveCount(1);

    await page.locator(".model-trigger").click();
    await page.getByRole("option", { name: /qwen\/qwen3.5-397b-a17b/ }).click();

    await expect(page.getByTestId("attach-strip")).toHaveCount(0);
  });

  test("auto-scroll follows stream when viewport stays at bottom", async ({ page }) => {
    await mockChunkedSseFromFixture(page, "stream-multi-token.txt");
    await page.goto("/");

    await sendMessage(page, "long stream");
    await expect(page.getByText("chunk-10")).toBeVisible();
    await waitForFollowState(page);
    await expect(page.getByText("chunk-40")).toBeVisible();
    await waitForFollowState(page);
  });

  test("manual scroll-up disables follow for subsequent streamed responses", async ({ page }) => {
    await mockChunkedSseFromFixture(page, "stream-multi-token.txt");
    await page.goto("/");
    const streamBodies = page.locator(".msg.assistant.stream .assistant-body");

    await sendMessage(page, "warmup long stream");
    await expect(streamBodies.last()).toContainText("chunk-40");
    await sendMessage(page, "first long stream");
    await expect(streamBodies.last()).toContainText("chunk-40");

    await scrollMessagesList(page, "top");
    await waitForDistanceAbove(page);

    await sendMessage(page, "second long stream");
    await expect(streamBodies.last()).toContainText("chunk-10");
    await expect(streamBodies.last()).toContainText("chunk-40");
    await waitForDistanceAbove(page);
  });

  test("completed answers do not show loading state during new stream", async ({ page }) => {
    let requestCount = 0;
    await page.route("**/api/chat/stream*", async (route) => {
      requestCount += 1;
      const answer = requestCount === 1 ? "First answer done" : "Second answer done";
      const body = [
        `data: {"type":"token","content":"${answer}"}`,
        "",
        `data: {"type":"done","finish_reason":"stop"}`,
        "",
      ].join("\n");
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body,
        headers: { "cache-control": "no-cache", connection: "keep-alive" },
      });
    });

    await page.goto("/");
    const messagesList = page.getByTestId("messages-list");

    await sendMessage(page, "question one");
    await expect(messagesList.getByText("First answer done")).toBeVisible();

    await sendMessage(page, "question two");
    await expect(messagesList.getByText("Second answer done")).toBeVisible();

    const streamMessages = messagesList.locator(".msg.assistant.stream");
    await expect(streamMessages).toHaveCount(2);

    const firstMsg = streamMessages.nth(0);
    await expect(firstMsg.locator(".typing-dots")).toHaveCount(0);
    await expect(firstMsg).toHaveClass(/stream-done/);
    await expect(firstMsg).not.toContainText("Thinking...");

    const secondMsg = streamMessages.nth(1);
    await expect(secondMsg).toHaveClass(/stream-done/);
    await expect(secondMsg.locator(".typing-dots")).toHaveCount(0);
  });
});
