import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
export default defineConfig({
  testDir: "../tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5188",
    launchOptions: {
      executablePath:
        process.env.CHROME_BIN || (existsSync(chrome) ? chrome : undefined),
    },
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "python3 ../scripts/integration/dev.py --test",
    url: "http://127.0.0.1:5188",
    reuseExistingServer: false,
    timeout: 45000,
    gracefulShutdown: { signal: "SIGTERM", timeout: 6000 },
  },
});
