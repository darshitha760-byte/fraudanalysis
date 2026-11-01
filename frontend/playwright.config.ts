import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `python "${resolve("..", "scripts", "serve_frontend_e2e.py")}"`,
      url: "http://127.0.0.1:8765/health",
      timeout: 120000,
      reuseExistingServer: false,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      env: { API_PROXY_TARGET: "http://127.0.0.1:8765" },
      timeout: 60000,
      reuseExistingServer: false,
    },
  ],
});
