import { test, expect } from "@playwright/test";
import { login, logout } from "./helpers";

test("transactions filter correctly, open details, and analytics render backend records", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Transactions", exact: true }).click();
  await page.getByLabel("Transaction ID", { exact: true }).fill("E2E-00001");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "E2E-00001", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("E2E-00001");
  await page.getByRole("button", { name: "Close details" }).click();
  await page.getByRole("link", { name: "Risk analytics", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer risk profiles" })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await logout(page);
});

test("rule changes and team role updates persist after reload", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Detection rules", exact: true }).click();
  const toggle = page.getByRole("switch", { name: "High value payment enabled" });
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect(toggle).not.toBeChecked();
  await page.reload();
  await expect(toggle).not.toBeChecked();
  await toggle.click();
  await expect(toggle).toBeChecked();
  await page.getByRole("link", { name: "Team members", exact: true }).click();
  const role = page.getByLabel("Role for viewer@example.com");
  await role.selectOption("analyst");
  await expect(role).toHaveValue("analyst");
  await page.reload();
  await expect(role).toHaveValue("analyst");
  await role.selectOption("viewer");
  await expect(role).toHaveValue("viewer");
  await page.getByRole("link", { name: "Audit trail", exact: true }).click();
  await expect(page.getByRole("cell", { name: "Update User", exact: true }).first()).toBeVisible();
  await logout(page);
});

test("alert decision is persisted and read back in the resolved queue", async ({ page }) => {
  await login(page, "analyst");
  await page.getByRole("link", { name: "Fraud alerts", exact: true }).click();
  await page.getByRole("button", { name: "ALT-1", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("80 / 100");
  await page.getByLabel("Justification").fill("Verified with the customer; transaction is legitimate.");
  await page.getByRole("button", { name: "Save review decision" }).click();
  await expect(page.getByRole("status").filter({ hasText: "review decision has been saved" })).toBeVisible();
  await page.getByRole("combobox", { name: /^Status/ }).selectOption("RESOLVED");
  await expect(page.getByRole("button", { name: "ALT-1", exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("combobox", { name: /^Status/ }).selectOption("RESOLVED");
  await expect(page.getByRole("button", { name: "ALT-1", exact: true })).toBeVisible();
  await logout(page);
});
