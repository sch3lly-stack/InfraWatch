// Generates README screenshots (simulated data). Run: SCREENSHOTS=1 npx playwright test screenshots
import { test } from "@playwright/test";

test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1");
test.use({ viewport: { width: 1280, height: 900 } });

test("screenshots", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("e2e-admin-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByLabel("Show simulated data").check();
  await page.waitForTimeout(800);
  await page.screenshot({ path: "../docs/screenshots/overview.png", fullPage: true });
  await page.getByRole("link", { name: "sim-web-01" }).first().click();
  await page.getByLabel("Time range").selectOption("6h");
  await page.waitForTimeout(800);
  const svg = page.getByTestId("chart-CPU utilization").locator("svg");
  const b = (await svg.boundingBox())!;
  await page.mouse.move(b.x + b.width * 0.7, b.y + b.height / 2);
  await page.screenshot({ path: "../docs/screenshots/host-detail.png", fullPage: true });
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: "../docs/screenshots/alerts.png", fullPage: true });
});
