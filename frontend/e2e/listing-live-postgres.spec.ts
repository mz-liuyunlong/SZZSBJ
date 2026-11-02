import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

const api = process.env.LISTING_LIVE_API_BASE;
test.skip(!api, "Requires the disposable PostgreSQL + FastAPI Listing sandbox");

test("Listing page persists GPT links, archive state, tags, and scoped CSV", async ({ page }) => {
  test.setTimeout(90_000);
  const errors: string[] = [];
  let listingReads = 0;
  let failNextListingRead = false;
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
          "action:products:listing-management:archive",
          "action:products:listing-management:restore",
          "action:products:listing-management:edit-analysis-link",
        ],
      },
      error: null, meta: null, request_id: "synthetic-auth-request",
    }),
  }));
  await page.route("**/api/listings/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/listings/walmart") {
      listingReads += 1;
      if (failNextListingRead) {
        failNextListingRead = false;
        await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
        return;
      }
    }
    await route.continue({ url: new URL(url.pathname + url.search, api).toString() });
  });

  await page.goto("/#/products/listing-management");
  await expect(page.getByRole("heading", { name: "Listing管理" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("SYNTHETIC-LISTING-A", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A2", { exact: true }) })
    .getByText("2026-10-14", { exact: true })).toBeVisible();
  await expect(page.getByText("SYNTHETIC-LISTING-B", { exact: true })).toHaveCount(0);
  await page.getByRole("row").filter({
    has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }),
  }).getByRole("button", { name: "详情" }).click();
  await page.getByRole("dialog", { name: "Listing 详情" })
    .getByRole("button", { name: "经营分析" }).click();
  const analysisDialog = page.getByRole("dialog", { name: "Listing经营分析中心" });
  await expect(analysisDialog).toContainText("已核实字段概览");
  await expect(analysisDialog).toContainText("未知数据不会视为零");
  await expect(analysisDialog).toContainText("暂不展示示例数字或模拟事件");
  await expect(analysisDialog).not.toContainText("Multipurpose Storage Bags");
  await analysisDialog.getByRole("button", { name: "关闭" }).click();
  const skuHeader = page.getByRole("columnheader", { name: /SKU\/MSKU/ }).locator(".ant-table-column-sorters");
  const ascendingSort = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/listings/walmart"
      && url.searchParams.get("sort_field") === "skuMsku"
      && url.searchParams.get("sort_order") === "asc";
  });
  await skuHeader.click();
  expect((await ascendingSort).status()).toBe(200);
  await expect(page.locator(".ant-table-tbody .ant-table-row").first()
    .getByText("SYNTHETIC-LISTING-A", { exact: true }).first()).toBeVisible();
  const descendingSort = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/api/listings/walmart"
      && url.searchParams.get("sort_field") === "skuMsku"
      && url.searchParams.get("sort_order") === "desc";
  }, { timeout: 15000 });
  await skuHeader.click();
  expect((await descendingSort).status()).toBe(200);
  await expect(page.locator(".ant-table-tbody .ant-table-row").first()).toContainText("SYNTHETIC-LISTING-A2");

  failNextListingRead = true;
  await page.getByRole("button", { name: /^在售商品：/ }).click();
  const retryLoad = page.getByRole("button", { name: /数据加载失败，点击重试/ });
  await expect(retryLoad).toBeVisible();
  await expect(page.getByText("SYNTHETIC-LISTING-A2", { exact: true }).first()).toBeVisible();
  await retryLoad.click();
  await expect(retryLoad).toHaveCount(0);
  await page.getByRole("button", { name: /^Listing总数：/ }).click();
  await expect(page.getByText("SYNTHETIC-LISTING-A", { exact: true }).first()).toBeVisible();

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

  const tagRow = page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }) });
  await tagRow.getByRole("checkbox").check();
  await page.getByRole("button", { name: "批量操作" }).click();
  await page.getByRole("menuitem", { name: "设置标签" }).click();
  const tagDialog = page.getByRole("dialog", { name: /设置标签/ });
  await tagDialog.getByRole("button", { name: "SyntheticTag" }).click();
  await tagDialog.getByRole("button", { name: /确\s*定/ }).click();
  await expect(tagDialog).toHaveCount(0);
  await page.reload({ waitUntil: "domcontentloaded" });
  const assignedRow = page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }) });
  await expect(assignedRow.getByText("SyntheticTag", { exact: true })).toBeVisible();
  await assignedRow.getByRole("checkbox").check();
  await page.getByRole("button", { name: "批量操作" }).click();
  await page.getByRole("menuitem", { name: "设置标签" }).click();
  const clearTagDialog = page.getByRole("dialog", { name: /设置标签/ });
  await clearTagDialog.getByRole("radio", { name: /替换/ }).check();
  await clearTagDialog.getByRole("button", { name: /确\s*定/ }).click();
  await page.getByRole("dialog", { name: "确认替换标签" })
    .getByRole("button", { name: /确\s*认\s*执\s*行/ }).click();
  await expect(clearTagDialog).toHaveCount(0);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }) })
    .getByText("SyntheticTag", { exact: true })).toHaveCount(0);

  const activeRow = page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }) });
  await activeRow.locator(".listing-management__gpt-analysis-button").focus();
  await page.keyboard.press("Enter");
  const gptDialog = page.getByRole("dialog", { name: /GPT分析链接/ });
  await gptDialog.getByLabel("关键词分析链接").fill("https://example.invalid/synthetic-keyword");
  await gptDialog.getByLabel("广告分析链接").fill("https://example.invalid/synthetic-ad");
  await gptDialog.getByRole("button", { name: /保\s*存/ }).click();
  await expect(gptDialog).toHaveCount(0);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }) })
    .locator(".listing-management__gpt-analysis-button").focus();
  await page.keyboard.press("Enter");
  const restoredGptDialog = page.getByRole("dialog", { name: /GPT分析链接/ });
  await expect(restoredGptDialog.getByLabel("关键词分析链接")).toHaveValue("https://example.invalid/synthetic-keyword");
  await expect(restoredGptDialog.getByLabel("广告分析链接")).toHaveValue("https://example.invalid/synthetic-ad");
  await restoredGptDialog.getByRole("button", { name: /取\s*消/ }).click();

  await page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }) })
    .getByRole("button", { name: "归档" }).click();
  await page.getByRole("button", { name: /确\s*认\s*归\s*档/ }).click();
  const archiveDialog = page.getByRole("dialog", { name: "填写归档原因" });
  await archiveDialog.getByPlaceholder(/请输入归档原因/).fill("Synthetic archive reason");
  const summaryAfterArchive = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/listings/walmart/summary");
  await archiveDialog.getByRole("button", { name: /确\s*认\s*归\s*档/ }).click();
  expect((await summaryAfterArchive).status()).toBe(200);
  await expect(archiveDialog).toHaveCount(0);
  await page.reload({ waitUntil: "domcontentloaded" });
  await archiveFilter.click();
  await page.getByRole("option", { name: "已归档" }).click();
  await page.getByRole("button", { name: "确定" }).click();
  const archivedRow = page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }) });
  await expect(archivedRow.getByText("Synthetic archive reason")).toBeVisible();
  await archivedRow.getByRole("button", { name: "恢复" }).click();
  const summaryAfterRestore = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/listings/walmart/summary");
  await page.getByRole("button", { name: /确\s*认\s*恢\s*复/ }).click();
  expect((await summaryAfterRestore).status()).toBe(200);
  await expect(archivedRow).toHaveCount(0);
  await archiveFilter.click();
  await page.getByRole("button", { name: "清空" }).click();
  await page.getByRole("button", { name: "确定" }).click();
  await expect(page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }) })).toBeVisible();
  await expect(page.getByText("Synthetic archive reason")).toHaveCount(0);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("row").filter({ has: page.getByText("SYNTHETIC-LISTING-A", { exact: true }) })).toBeVisible();
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
  expect((await (await page.request.post(`${api}/__listing_test__/seed_extra`)).json()).seeded).toBe(49);
  await page.evaluate(() => {
    localStorage.setItem("szzsbj_auth_token", "synthetic-listing-a");
    const prefix = "szzsbj:page-state:listing-management:synthetic-listing-user-a:";
    sessionStorage.setItem(`${prefix}pageSize`, "50");
    sessionStorage.setItem(`${prefix}currentPage`, "1");
    sessionStorage.setItem(`${prefix}appliedColumnKeys`, JSON.stringify(["skuMsku", "sales90Days"]));
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("columnheader", { name: "近30天销量" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "近90天销量" })).toHaveCount(0);
  await expect(page.locator(".ant-table-tbody .ant-table-row")).toHaveCount(50);
  await page.locator(".ant-table-tbody .ant-table-row").first().getByRole("checkbox").check();
  await expect(page.getByText("已选择 1 项")).toBeVisible();
  await page.locator(".ant-pagination-item-2").click();
  await expect(page.locator(".ant-table-tbody .ant-table-row")).toHaveCount(1);
  await expect(page.getByText("已选择 1 项")).toBeVisible();
  await page.locator(".ant-table-tbody .ant-table-row").first().getByRole("checkbox").check();
  await expect(page.getByText("已选择 2 项")).toBeVisible();
  await page.getByRole("button", { name: "批量操作" }).click();
  await page.getByRole("menuitem", { name: "导出已选" }).click();
  const crossPageDownload = page.waitForEvent("download");
  await page.getByRole("dialog", { name: /导出数据/ }).getByRole("button", { name: /导\s*出/ }).click();
  const crossPageCsv = await readFile(await (await crossPageDownload).path(), "utf-8");
  expect(crossPageCsv.trim().split(/\r?\n/)).toHaveLength(3);
  expect(crossPageCsv).not.toContain("SYNTHETIC-LISTING-B");

  await page.getByRole("button", { name: "批量操作" }).click();
  await page.getByRole("menuitem", { name: "批量归档" }).click();
  const batchArchiveDialog = page.getByRole("dialog", { name: "批量归档 2 个 Listing" });
  await batchArchiveDialog.getByPlaceholder(/请输入归档原因/).fill("Synthetic cross-page archive");
  await batchArchiveDialog.getByRole("button", { name: "确认批量归档" }).click();
  await expect(batchArchiveDialog).toHaveCount(0);
  await expect(page.getByText("已选择 2 项")).toHaveCount(0);
  await archiveFilter.click();
  await page.getByRole("option", { name: "已归档" }).click();
  await page.getByRole("button", { name: "确定" }).click();
  await expect(page.locator(".ant-table-tbody .ant-table-row")).toHaveCount(2);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".ant-table-tbody .ant-table-row")).toHaveCount(2);
  await page.locator(".ant-table-tbody .ant-table-row").nth(0).getByRole("checkbox").check();
  await page.locator(".ant-table-tbody .ant-table-row").nth(1).getByRole("checkbox").check();
  await page.getByRole("button", { name: "批量操作" }).click();
  await page.getByRole("menuitem", { name: "批量恢复" }).click();
  const batchRestoreDialog = page.getByRole("dialog", { name: "批量恢复 2 个 Listing" });
  await batchRestoreDialog.getByRole("button", { name: "确认恢复" }).click();
  await expect(batchRestoreDialog).toHaveCount(0);
  await expect(page.locator(".ant-table-tbody .ant-table-row")).toHaveCount(0);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".ant-table-tbody .ant-table-row")).toHaveCount(0);

  expect(listingReads).toBeGreaterThanOrEqual(2);
  expect(errors).toEqual([]);
});
