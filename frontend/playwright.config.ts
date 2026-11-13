import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  workers: 1,
  use: { baseURL: "http://localhost:8765", screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: {
    command: "../scripts/e2e_server.sh",
    url: "http://localhost:8765/api/v1/health",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
