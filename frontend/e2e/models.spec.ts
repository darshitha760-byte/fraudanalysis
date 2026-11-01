import { test, expect } from "@playwright/test";
import { login, logout } from "./helpers";

test("train real demo models, read saved metrics, compare and retain them after reload", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Model studio", exact: true }).click();
  await page.getByRole("button", { name: "Train a model", exact: true }).click();
  await page.getByLabel("Data source").selectOption("synthetic");
  await expect(page.getByRole("dialog")).toContainText("without adding transactions");
  await page.getByRole("checkbox", { name: /Logistic Regression/ }).check();
  await page.getByRole("checkbox", { name: /Isolation Forest/ }).check();
  const finished = page.waitForResponse((response) => response.url().endsWith("/api/models/train") && response.request().method() === "POST", { timeout: 120000 });
  await page.getByRole("button", { name: "Start training", exact: true }).click();
  const response = await finished;
  expect(response.status()).toBe(201);
  const body = await response.json();
  expect(body.items).toHaveLength(3);
  expect(body.data_split).toEqual({ train: 700, val: 100, test: 200 });
  await expect(page.getByText("3 model(s) trained and saved", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Validation breakdown" })).toBeVisible();
  await expect(page.getByText("Synthetic demonstration data", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Compare models" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Model studio", exact: true })).toBeVisible();
  await expect(page.getByLabel("Saved model").locator("option")).toHaveCount(3);
  await page.getByRole("tab", { name: "Training history" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await logout(page);
});

test("analyst trains on labeled database data and configuration prevents empty algorithm selection", async ({ page }) => {
  await login(page, "analyst");
  await page.getByRole("link", { name: "Model studio", exact: true }).click();
  await page.getByRole("button", { name: "Train a model", exact: true }).click();
  await page.getByRole("checkbox", { name: /Random Forest/ }).uncheck();
  await expect(page.getByRole("button", { name: "Start training", exact: true })).toBeDisabled();
  await page.getByRole("checkbox", { name: /Logistic Regression/ }).check();
  await page.getByRole("button", { name: "Start training", exact: true }).click();
  await expect(page.getByText("1 model(s) trained and saved", { exact: false })).toBeVisible({ timeout: 120000 });
  await expect(page.getByText("Labeled database data", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Saved model").locator("option")).toHaveCount(4);
  await logout(page);
});
