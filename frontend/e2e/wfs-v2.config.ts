import { defineConfig } from "@playwright/test";
import { resolve, join } from "node:path";
import { tmpdir } from "node:os";

const frontend = resolve(import.meta.dirname, "..");
const database = "postgresql+psycopg://wfs_test@127.0.0.1:56543/wfs_v2_test_run";
export default defineConfig({
  timeout: 240000, expect: { timeout: 45000 },
  testDir: ".", testMatch: "wfs-v2-live.spec.ts", workers: 1,
  outputDir: join(tmpdir(), "szzsbj-wfs-v2-live-results"),
  use: { baseURL: "http://127.0.0.1:4178", channel: "msedge", viewport: { width: 1600, height: 1050 }, trace: "retain-on-failure" },
  webServer: [
    { command: `"${resolve(frontend, "../backend/.venv/Scripts/python.exe")}" -m uvicorn tests.modules.pmc_wfs.v2_server:app --host 127.0.0.1 --port 8018`, cwd: resolve(frontend, "../backend"), url: "http://127.0.0.1:8018/health", reuseExistingServer: false,
      env: { APP_ENV: "test", TEST_DATABASE_URL: database, WFS_V2_TEST_DATABASE_URL: database } },
    { command: "node node_modules/vite/bin/vite.js --config e2e/wfs-v2.vite.config.ts", cwd: frontend, url: "http://127.0.0.1:4178", reuseExistingServer: false },
  ],
});
