import { expect, test } from "@playwright/test";
import { mockSseFromFixture, sendMessage } from "../helpers/mockSse";

async function getDistanceToBottom(page) {
  return page.locator("[data-testid='messages-list']").evaluate((el) => {
    return el.scrollHeight - el.scrollTop - el.clientHeight;
  });
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
    await mockSseFromFixture(page, "stream-multi-token.txt");
    await page.goto("/");

    await sendMessage(page, "long stream");
    await expect(page.getByText("chunk-40")).toBeVisible();

    const distanceToBottom = await getDistanceToBottom(page);
    expect(distanceToBottom).toBeLessThanOrEqual(150);
  });

  test("manual scroll-up disables follow until user scrolls back", async ({ page }) => {
    await mockSseFromFixture(page, "stream-multi-token.txt");
    await page.goto("/");
    const streamBodies = page.locator(".msg.assistant.stream .assistant-body");
    const list = page.locator("[data-testid='messages-list']");

    await sendMessage(page, "warmup long stream");
    await expect(streamBodies.last()).toContainText("chunk-40");
    await sendMessage(page, "first long stream");
    await expect(streamBodies.last()).toContainText("chunk-40");

    await list.evaluate((el) => {
      el.scrollTop = 0;
      el.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect.poll(() => getDistanceToBottom(page)).toBeGreaterThan(150);

    await sendMessage(page, "second long stream");
    await expect(streamBodies.last()).toContainText("chunk-40");
    await expect.poll(() => getDistanceToBottom(page)).toBeGreaterThan(150);

    await list.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
      el.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect.poll(() => getDistanceToBottom(page), { timeout: 10000 }).toBeLessThanOrEqual(5);

    await sendMessage(page, "third long stream");
    await expect(streamBodies.last()).toContainText("chunk-40");
    await expect.poll(() => getDistanceToBottom(page)).toBeLessThanOrEqual(150);
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
