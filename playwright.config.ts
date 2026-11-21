import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

const database = join(
  mkdtempSync(join(tmpdir(), "undercover-e2e-")),
  "claims.sqlite3",
);
const backendUrl = "http://127.0.0.1:8001";

export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e/test-results",
  reporter: "list",
  workers: 1,
  use: { baseURL: "http://127.0.0.1:5174", trace: "retain-on-failure" },
  webServer: [
    {
      command:
        "uv run -m uvicorn backend.main:app --host 127.0.0.1 --port 8001",
      env: { UNDERCOVER_DB: database },
      url: `${backendUrl}/api/health`,
      reuseExistingServer: false,
    },
    {
      command: "npx vite dashboard --host 127.0.0.1 --port 5174 --strictPort",
      env: { BACKEND_URL: backendUrl },
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
    },
  ],
});
