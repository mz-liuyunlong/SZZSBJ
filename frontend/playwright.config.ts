import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";

export default defineConfig({
  workers: process.env.CI ? 1 : undefined,
  outputDir: join(tmpdir(), "szzsbj-playwright-test-results"),
  testDir: "./e2e",
  // Runs only through e2e/wfs-v2.config.ts (own backend + isolated database).
  testIgnore: ["wfs-v2-live.spec.ts"],
  use: {
    baseURL: "http://127.0.0.1:4173",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
  },
});
