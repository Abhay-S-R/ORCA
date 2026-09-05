import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Day 21 a11y CI gate (plan §6 D1 Day 21, acceptance row 5: "axe-core zero
// criticals in CI"). D1 owns this harness and audits its own two named
// flows — Ask (`/ask`) and Safety (`/safety`); D2/D3 add their own spec files
// against the same AxeBuilder + config for /watches, /ops, /map, /voyage,
// /reasoning. NVDA keyboard/screen-reader passes are a separate manual
// step recorded per-flow (not automatable in a headless CI runner).
async function expectNoCriticalViolations(page: import("@playwright/test").Page, label: string) {
  const results = await new AxeBuilder({ page }).analyze();
  const critical = results.violations.filter((v) => v.impact === "critical");
  expect(critical, `${label}: ${JSON.stringify(critical, null, 2)}`).toEqual([]);
}

test.describe("Ask flow (/ask)", () => {
  test("empty state has no critical a11y violations", async ({ page }) => {
    await page.goto("/ask");
    await expect(page.getByRole("heading", { name: "Ask about conditions at sea" })).toBeVisible();
    await expectNoCriticalViolations(page, "Ask — empty state");
  });

  test("persona switcher selection has no critical a11y violations", async ({ page }) => {
    await page.goto("/ask");
    // A native <select> — its popup is OS-rendered and outside Playwright's
    // DOM snapshot, so exercise it via selectOption rather than click+visible.
    await page.getByRole("combobox", { name: "Viewing as" }).selectOption("fisherman");
    await expect(page.getByRole("combobox", { name: "Viewing as" })).toHaveValue("fisherman");
    await expectNoCriticalViolations(page, "Ask — persona switched to fisherman");
  });

  test("query input and submit button are reachable by keyboard", async ({ page }) => {
    await page.goto("/ask");
    const input = page.getByRole("textbox", { name: "Your question about marine conditions" });
    await input.fill("Is it safe to go out tomorrow morning?"); // enables the submit button — disabled buttons never receive focus
    await input.focus();
    await expect(input).toBeFocused();
    // The voice mic sits between the box and Ask — both feed the same query,
    // so it is in tab order by design. Walking both hops asserts the order
    // *and* that the mic carries an accessible name.
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: /ask by voice/i })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Ask", exact: true })).toBeFocused();
  });
});

test.describe("Safety flow (/safety)", () => {
  test("empty state has no critical a11y violations", async ({ page }) => {
    await page.goto("/safety");
    await expect(page.getByRole("heading", { name: "Can I go out?" })).toBeVisible();
    await expectNoCriticalViolations(page, "Safety — empty state");
  });

  test("vessel class selection has no critical a11y violations", async ({ page }) => {
    await page.goto("/safety");
    await page.getByRole("combobox", { name: "Vessel class" }).selectOption("cargo_vessel");
    await expect(page.getByRole("combobox", { name: "Vessel class" })).toHaveValue("cargo_vessel");
    await expectNoCriticalViolations(page, "Safety — vessel class switched to cargo vessel");
  });
});
