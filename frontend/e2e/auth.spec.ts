import { test, expect } from "@playwright/test";
import { login, logout } from "./helpers";

test("login errors are explicit; valid login survives reload and logout clears it", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email address").fill("admin@example.com");
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid email or password");
  await login(page);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Risk operations overview" })).toBeVisible();
  await logout(page);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Welcome back." })).toBeVisible();
});

test("viewer can use analytics but cannot enter admin pages or train", async ({ page }) => {
  await login(page, "viewer");
  await page.getByRole("link", { name: "Risk analytics", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer risk profiles" })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("link", { name: "Model studio", exact: true }).click();
  await expect(page.getByRole("button", { name: "Train a model", exact: true })).toHaveCount(0);
  await page.goto("/users");
  await expect(page.getByRole("alert")).toContainText("restricted");
  await logout(page);
});

test("registration persists a viewer account and permits a subsequent sign in", async ({ page }) => {
  const email = `browser-${Date.now()}@example.com`;
  await page.goto("/");
  await page.getByRole("button", { name: "Create an account", exact: true }).click();
  await page.getByLabel("Full name").fill("New Viewer");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("New-Viewer-Test-2026");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("viewer account is ready");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("New-Viewer-Test-2026");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(page.getByText("New Viewer", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("viewer account", { exact: true })).toBeVisible();
  await logout(page);
});

test("mobile navigation fits the viewport and session expiration returns to sign in", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "viewer");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Risk analytics", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Risk analytics", exact: true })).toBeVisible();
  await page.evaluate(() => sessionStorage.setItem("foresight_session", "expired"));
  await page.reload();
  await expect(page.getByRole("heading", { name: "Welcome back." })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("session expired");
});
