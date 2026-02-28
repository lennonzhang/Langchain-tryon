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
    await sendMessage(page, "hello");

    await expect(page.getByText("Hello from SSE")).toBeVisible();
    await expect(page.getByText(/\[single\] 120\/128000 tokens/)).toBeVisible();
  });

  test("renders search and reasoning sections", async ({ page }) => {
    await mockSseFromFixture(page, "stream-search-reasoning.txt");
    await page.goto("/");

    await page.locator("#searchToggle").check({ force: true });
    await sendMessage(page, "find docs");

    await expect(page.getByTestId("search-panel")).toBeVisible();
    await expect(page.getByTestId("reasoning-panel")).toBeVisible();
    await expect(page.getByText("Final answer from agent mode.")).toBeVisible();
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

    await sendMessage(page, "first long stream");
    await expect(page.locator(".msg.assistant.stream .assistant-body").last()).toContainText("chunk-40");

    const list = page.locator("[data-testid='messages-list']");
    await list.evaluate((el) => {
      el.scrollTop = Math.max(0, el.scrollTop - 400);
      el.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    const distanceAfterScrollUp = await getDistanceToBottom(page);
    expect(distanceAfterScrollUp).toBeGreaterThan(150);

    await sendMessage(page, "second long stream");
    await expect(page.locator(".msg.assistant.stream .assistant-body").last()).toContainText("chunk-40");

    const distanceAfterSecond = await getDistanceToBottom(page);
    expect(distanceAfterSecond).toBeGreaterThan(150);

    await list.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
      el.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    await sendMessage(page, "third long stream");
    await expect(page.locator(".msg.assistant.stream .assistant-body").last()).toContainText("chunk-40");

    const distanceAfterResume = await getDistanceToBottom(page);
    expect(distanceAfterResume).toBeLessThanOrEqual(150);
  });
});
