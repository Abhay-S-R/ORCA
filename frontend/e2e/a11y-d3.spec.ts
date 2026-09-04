import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Day 21 a11y CI gate (plan §6 D3, acceptance row 5/scenario F) — D3's own
// three flows against the same AxeBuilder + config a11y.spec.ts (D1) uses:
// /map, /voyage, /reasoning. See that file's header comment for the split.
async function expectNoCriticalViolations(page: import("@playwright/test").Page, label: string) {
  const results = await new AxeBuilder({ page }).analyze();
  const critical = results.violations.filter((v) => v.impact === "critical");
  expect(critical, `${label}: ${JSON.stringify(critical, null, 2)}`).toEqual([]);
}

test.describe("Map flow (/map)", () => {
  test("empty state has no critical a11y violations", async ({ page }) => {
    await page.goto("/map");
    await expect(page.getByRole("heading", { name: "Chart" })).toBeAttached();
    await expectNoCriticalViolations(page, "Map — empty state");
  });

  test("chart layers control is reachable by keyboard", async ({ page }) => {
    await page.goto("/map");
    const layersButton = page.getByRole("button", { name: "Chart layers" });
    await layersButton.focus();
    await expect(layersButton).toBeFocused();
    await page.keyboard.press("Enter");
    await expectNoCriticalViolations(page, "Map — layers panel open");
  });
});

test.describe("Voyage flow (/voyage)", () => {
  test("empty state has no critical a11y violations", async ({ page }) => {
    await page.goto("/voyage");
    await expect(page.getByRole("heading", { name: "Plan a voyage" })).toBeVisible();
    await expectNoCriticalViolations(page, "Voyage — empty state");
  });

  test("vessel class selection has no critical a11y violations", async ({ page }) => {
    await page.goto("/voyage");
    const vesselClass = page.getByRole("combobox", { name: "Vessel class" });
    await vesselClass.selectOption("mechanized_trawler");
    await expect(vesselClass).toHaveValue("mechanized_trawler");
    await expectNoCriticalViolations(page, "Voyage — vessel class switched");
  });
});

test.describe("Reasoning flow (/reasoning)", () => {
  test("empty state (example trace) has no critical a11y violations", async ({ page }) => {
    await page.goto("/reasoning");
    await expect(page.getByRole("heading", { name: "Reasoning", exact: true })).toBeVisible();
    await expectNoCriticalViolations(page, "Reasoning — example trace");
  });

  test("Ask ORCA input and Run button are reachable by keyboard", async ({ page }) => {
    await page.goto("/reasoning");
    const input = page.getByRole("textbox", { name: "Ask ORCA" });
    await input.focus();
    await expect(input).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Run" })).toBeFocused();
  });

  test("graph nodes are keyboard-navigable and the inspector is dismissible", async ({ page }) => {
    await page.goto("/reasoning");
    // React Flow's own node group is focusable and Enter-selectable (plan
    // §7's "keyboard-navigable node to node, inspector reachable and
    // dismissible without a mouse" requirement). Matched by attribute, not
    // accessible name — React Flow's node group carries no aria-label, only
    // aria-roledescription="node" plus a describedby. Excludes the
    // non-selectable fan-out group boxes (dagre-layout.ts sets
    // selectable: false on those, and they render first in DOM order).
    const firstNode = page.locator('[role="group"][aria-roledescription="node"]', { hasNotText: "parallel fan-out" }).first();
    // fitView's initial pan/zoom takes a moment to settle after mount;
    // focusing and pressing Enter before it does risks acting on a node
    // that's about to move out from under the (already-resolved) locator.
    await page.waitForTimeout(300);
    await firstNode.focus();
    await page.keyboard.press("Enter");
    // "Inspector" is only the panel's title in the *unselected* state (it
    // becomes the node's own agent_name once selected) — asserting on it
    // here would pass trivially without ever proving selection happened.
    // The close button only renders once a node is actually selected, so
    // waiting on it is the real signal.
    const closeButton = page.getByRole("button", { name: /close inspector/i });
    await expect(closeButton).toBeVisible();
    await closeButton.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("Select a node to see its full reasoning")).toBeVisible();
  });
});
