import { defineConfig, devices } from "@playwright/test";

// Day 21 a11y CI gate (plan §6 D1, harness owned by D1; each slice adds its
// own flows here — D2: /watches, /ops; D3: /map, /voyage, /reasoning).
// No backend dependency: CI runs on a hosted runner with no Tier-1 data
// fixtures (see .github/workflows/ci.yml), so these assert on markup and
// keyboard/ARIA state reachable without a live multi-agent query — the
// same constraint the existing pytest job already documents.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: process.env.CI ? 2 : 2,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
