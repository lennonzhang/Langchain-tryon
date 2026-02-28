import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./tests",
  timeout: 45_000,
  expect: {
    timeout: 7_000,
    toHaveScreenshot: {
      animations: "disabled",
      maxDiffPixelRatio: 0.01,
    },
  },
  fullyParallel: true,
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    viewport: { width: 1280, height: 900 },
    colorScheme: "light",
  },
  projects: [
    {
      name: "e2e-desktop",
      testMatch: /tests\/e2e\/.*\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "visual-desktop",
      testMatch: /tests\/visual\/.*\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "visual-mobile",
      testMatch: /tests\/visual\/.*\.spec\.ts/,
      use: { ...devices["Pixel 7"] },
    },
  ],
  webServer: {
    command: `pnpm dev --host 127.0.0.1 --port ${PORT}`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
