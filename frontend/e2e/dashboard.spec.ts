import { expect, Page, test } from "@playwright/test";

async function login(page: Page, user = "admin", pw = "e2e-admin-password") {
  await page.goto("/login");
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password").fill(pw);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("rejects bad credentials and redirects unauthenticated users", async ({ page }) => {
  await page.goto("/hosts");
  await expect(page).toHaveURL(/\/login/);
  await login(page, "admin", "wrong-password");
  await expect(page.getByRole("alert")).toContainText("invalid");
});

test("real data is separated from simulated data", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByTestId("stat-Monitored systems")).toContainText("0"); // no real agents registered
  await expect(page.getByText("No systems yet")).toBeVisible();
  await page.getByLabel("Show simulated data").check();
  await expect(page.getByTestId("stat-Monitored systems")).toContainText("6");
  await expect(page.getByText("SIMULATED").first()).toBeVisible();
});

test("overview, host detail with charts and services", async ({ page }) => {
  await login(page);
  await page.getByLabel("Show simulated data").check();
  await expect(page.getByTestId("stat-Offline")).toContainText("1");
  await page.getByRole("link", { name: "sim-web-01" }).first().click();
  await expect(page.getByRole("heading", { name: /sim-web-01/ })).toBeVisible();
  for (const t of ["CPU utilization", "Memory utilization", "Disk utilization", "Network throughput"])
    await expect(page.getByTestId(`chart-${t}`).locator("path[stroke]").first()).toBeVisible();
  // hover crosshair + tooltip
  const svg = page.getByTestId("chart-CPU utilization").locator("svg");
  const box = (await svg.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.getByTestId("chart-CPU utilization")).toContainText("CPU:");
  // time range switch reloads data
  await page.getByLabel("Time range").selectOption("6h");
  await expect(page.getByTestId("services")).toContainText("web");
  // table view alternative
  await page.getByTestId("chart-CPU utilization").getByRole("button", { name: "Table" }).click();
  await expect(page.getByTestId("chart-CPU utilization").locator("table")).toBeVisible();
});

test("alerts: acknowledge and resolve", async ({ page }) => {
  await login(page);
  await page.getByLabel("Show simulated data").check();
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  const rows = page.getByTestId("alert-row");
  await expect(rows.first()).toBeVisible();
  const n = await rows.count();
  await rows.first().getByRole("button", { name: "Acknowledge" }).click();
  await expect(page.getByTestId("alert-row").first()).toContainText("acknowledged");
  await page.getByTestId("alert-row").first().getByRole("button", { name: "Resolve" }).click();
  await expect(page.getByTestId("alert-row")).toHaveCount(n - 1);
  await page.getByLabel("Alert status").selectOption("resolved");
  await expect(page.getByTestId("alert-row").first()).toContainText("resolved");
});

test("admin can create rule and enrollment token; viewer cannot see settings", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByLabel("Rule name").fill("E2E CPU rule");
  await page.getByRole("button", { name: "Add rule" }).click();
  await expect(page.getByTestId("rule-row").filter({ hasText: "E2E CPU rule" })).toBeVisible();
  await page.getByRole("button", { name: "Create token" }).click();
  await expect(page.getByTestId("new-token")).toContainText("iwe_");
  await page.getByLabel("New username").fill("viewer1");
  await page.getByLabel("New password").fill("viewerpassword1");
  await page.getByRole("button", { name: "Add user" }).click();
  await expect(page.getByText("viewer1")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await login(page, "viewer1", "viewerpassword1");
  await expect(page.getByRole("link", { name: "Settings" })).toHaveCount(0);
  await page.getByRole("link", { name: "Alerts", exact: true }).click();
  await page.getByLabel("Show simulated data").check();
  await expect(page.getByRole("button", { name: "Acknowledge" })).toHaveCount(0); // viewers are read-only
});
