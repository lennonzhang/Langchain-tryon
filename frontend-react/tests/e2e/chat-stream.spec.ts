import { expect, test } from "@playwright/test";
import { mockSseFromFixture, sendMessage } from "../helpers/mockSse";

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

    await page.locator("#searchToggle").check();
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
});
