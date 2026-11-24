import { defineConfig } from "@playwright/test";

// Chromium only. `globalSetup` generates the toy report with the real CLI; run with `pnpm e2e`.
export default defineConfig({
  testDir: "tests/e2e",
  globalSetup: "./tests/e2e/global-setup.ts",
  reporter: "list",
  outputDir: "node_modules/.cache/playwright-results", // keeps artifacts out of git status
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
