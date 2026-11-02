import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

const api = process.env.LISTING_LIVE_API_BASE;
test.skip(!api, "Requires the disposable PostgreSQL + FastAPI Listing sandbox");

test("Listing page reads scoped MART, restores tags, and exports scoped CSV", async ({ page }) => {
  const errors: string[] = [];
  let listingReads = 0;
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    if (!localStorage.getItem("szzsbj_auth_token")) {
      localStorage.setItem("szzsbj_auth_token", "synthetic-listing-a");
    }
  });
  await page.route("**/api/auth/me", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      success: true,
      data: {
        id: route.request().headers().authorization === "Bearer synthetic-listing-b" ? 2 : 1,
        username: route.request().headers().authorization === "Bearer synthetic-listing-b"
          ? "synthetic-listing-user-b" : "synthetic-listing-user-a",
        display_name: "Synthetic Listing User",
        is_super_admin: false, role_keys: [], role_names: [],
        permissions: [
          "page:products:listing-management:view",
          "action:products:listing-management:manage-tags",
          "action:products:listing-management:export",
        ],
      },
      error: null, meta: null, request_id: "synthetic-auth-request",
    }),
  }));
  await page.route("**/api/listings/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/listings/walmart") listingReads += 1;
    await route.continue({ url: new URL(url.pathname + url.search, api).toString() });
  });

  await page.goto("/#/products/listing-management");
  await expect(page.getByRole("heading", { name: "Listing管理" })).toBeVisible();
  await expect(page.getByText("SYNTHETIC-LISTING-A", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A2", { exact: true }) })
    .getByText("2026-10-14", { exact: true })).toBeVisible();
  await expect(page.getByText("SYNTHETIC-LISTING-B", { exact: true })).toHaveCount(0);

  const archiveFilter = page.getByRole("combobox", { name: "归档状态" });
  await archiveFilter.click();
  await page.getByRole("option", { name: "未归档" }).click();
  await page.getByRole("button", { name: "确定" }).click();
  await expect(page.getByText("SYNTHETIC-LISTING-A", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("SYNTHETIC-LISTING-A2", { exact: true })).toHaveCount(0);
  await archiveFilter.click();
  await page.getByRole("button", { name: "清空" }).click();
  await page.getByRole("option", { name: "状态未确认" }).click();
  await page.getByRole("button", { name: "确定" }).click();
  await expect(page.getByText("SYNTHETIC-LISTING-A2", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("SYNTHETIC-LISTING-A", { exact: true })).toHaveCount(0);
  await archiveFilter.click();
  await page.getByRole("button", { name: "清空" }).click();
  await page.getByRole("button", { name: "确定" }).click();
  await expect(page.getByText("SYNTHETIC-LISTING-A", { exact: true }).first()).toBeVisible();

  const selectedRow = page.getByRole("row").filter({
    has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }),
  });
  await selectedRow.getByRole("checkbox").check();
  await page.getByRole("button", { name: "批量操作" }).click();
  await page.getByRole("menuitem", { name: "导出已选" }).click();
  const selectedExportDialog = page.getByRole("dialog", { name: /导出数据/ });
  const selectedDownload = page.waitForEvent("download");
  await selectedExportDialog.getByRole("button", { name: /导\s*出/ }).click();
  const selectedCsv = await readFile(await (await selectedDownload).path(), "utf-8");
  expect(selectedCsv).toContain("SYNTHETIC-LISTING-A");
  expect(selectedCsv).not.toContain("SYNTHETIC-LISTING-A2");
  expect(selectedCsv).not.toContain("SYNTHETIC-LISTING-B");
  await selectedRow.getByRole("checkbox").uncheck();

  await page.getByRole("button", { name: "标签管理" }).click();
  const dialog = page.getByRole("dialog", { name: "自定义标签管理" });
  await expect(dialog.getByText("SyntheticTag")).toBeVisible();
  const activation = page.waitForResponse((response) =>
    response.request().method() === "PATCH" && new URL(response.url()).pathname.startsWith("/api/listings/tags/"));
  await dialog.getByRole("button", { name: "启用" }).click();
  expect((await activation).status()).toBe(200);
  await expect(dialog.getByRole("button", { name: "停用" })).toBeVisible();
  await dialog.getByRole("button", { name: "关闭" }).click();
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByText("SYNTHETIC-LISTING-A", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "标签管理" }).click();
  await expect(page.getByRole("dialog", { name: "自定义标签管理" }).getByRole("button", { name: "停用" })).toBeVisible();
  await page.getByRole("dialog", { name: "自定义标签管理" }).getByRole("button", { name: "关闭" }).click();
  await page.getByRole("button", { name: "下载" }).click();
  const exportDialog = page.getByRole("dialog", { name: /导出数据/ });
  const download = page.waitForEvent("download");
  await exportDialog.getByRole("button", { name: /导\s*出/ }).click();
  const csv = await readFile(await (await download).path(), "utf-8");
  expect(csv).toContain("SYNTHETIC-LISTING-A");
  expect(csv).toContain("SYNTHETIC-LISTING-A2");
  expect(csv).not.toContain("SYNTHETIC-LISTING-B");
  await page.evaluate(() => localStorage.setItem("szzsbj_auth_token", "synthetic-listing-b"));
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByText("SYNTHETIC-LISTING-B", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("SYNTHETIC-LISTING-A", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "标签管理" }).click();
  await expect(page.getByRole("dialog", { name: "自定义标签管理" }).getByRole("button", { name: "启用" })).toBeVisible();
  expect(listingReads).toBeGreaterThanOrEqual(2);
  expect(errors).toEqual([]);
});
