import { expect, test } from "@playwright/test";
import {
  mockDelayedSseFromFixture,
  mockSseFromFixture,
  sendMessage,
  stabilizeForScreenshot,
} from "../helpers/mockSse";

test.describe("chat visual regression", () => {
  test("initial screen", async ({ page }) => {
    await page.goto("/");
    await stabilizeForScreenshot(page);
    await expect(page.locator(".chat")).toHaveScreenshot("chat-initial.png");
  });

  test("stream loading state", async ({ page }) => {
    // Delay response so screenshot captures a true in-flight pending state.
    await mockDelayedSseFromFixture(page, "stream-loading.txt", 1500);
    await page.goto("/");
    await sendMessage(page, "show loading");
    await expect(page.locator(".status-dot.busy")).toBeVisible();
    await stabilizeForScreenshot(page);
    await expect(page.locator(".chat")).toHaveScreenshot("chat-loading.png");
  });

  test("search + reasoning + answer state", async ({ page }) => {
    await mockSseFromFixture(page, "stream-search-reasoning.txt");
    await page.goto("/");
    await sendMessage(page, "show search and reasoning");
    await expect(page.getByTestId("search-panel")).toBeVisible();
    await expect(page.getByTestId("reasoning-panel")).toBeVisible();
    await stabilizeForScreenshot(page);
    await expect(page.locator(".chat")).toHaveScreenshot("chat-search-reasoning.png");
  });

  test("error state", async ({ page }) => {
    await mockSseFromFixture(page, "stream-error.txt");
    await page.goto("/");
    await sendMessage(page, "show error");
    await expect(page.getByText("Error: stream crashed")).toBeVisible();
    await stabilizeForScreenshot(page);
    await expect(page.locator(".chat")).toHaveScreenshot("chat-error.png");
  });

  test("attachment strip state", async ({ page }) => {
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
    await expect(page.getByTestId("attach-strip")).toBeVisible();
    await stabilizeForScreenshot(page);
    await expect(page.locator(".chat")).toHaveScreenshot("chat-attachments.png");
  });
});
