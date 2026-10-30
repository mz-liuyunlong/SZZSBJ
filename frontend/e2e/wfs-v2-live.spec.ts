/** Real local HTTP + PostgreSQL. Only platform and login identity are synthetic. */
import { expect, test } from "@playwright/test";

test.describe.configure({ mode: "serial" });
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "wfs-synthetic-e2e"));
  await page.goto("/#/pmc/wfs/pending-packing", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("checkbox", { name: /选择PK-E2E-MAIN/ })).toBeVisible();
});

test("partial shipment auto-approves and persists through browser reload", async ({ page }, info) => {
  await page.getByRole("checkbox", { name: /选择PK-E2E-MAIN/ }).check();
  await page.getByRole("button", { name: "创建 WFS 货件", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: /创建 WFS 货件/ });
  await dialog.getByRole("spinbutton", { name: "本次发货箱数", exact: true }).fill("20");
  await dialog.getByRole("spinbutton", { name: "计划货件数量", exact: true }).fill("2");
  await dialog.getByRole("spinbutton", { name: "货件1箱数" }).fill("12");
  await dialog.getByRole("spinbutton", { name: "货件2箱数" }).fill("8");
  await dialog.getByRole("button", { name: "核对分箱" }).click();
  await expect(dialog.getByText(/本次安排后剩余 10 箱/)).toBeVisible();
  await dialog.getByLabel("退货街道地址").fill("Synthetic street");
  await dialog.getByLabel("城市", { exact: true }).fill("Katy");
  await dialog.getByLabel("州代码").fill("TX");
  await dialog.getByLabel("邮编").fill("77449");
  await dialog.getByLabel("预计到仓日期（台北时间）").fill("2026-12-01");
  await expect(dialog.getByRole("button", { name: /审批/ })).toHaveCount(0);
  await dialog.getByRole("button", { name: "确认创建", exact: true }).click();
  const records = page.getByRole("dialog", { name: "创建记录", exact: true });
  await expect(records.getByText("程序自动审批通过")).toBeVisible();
  await expect(records.getByText("创建成功").first()).toBeVisible();
  await expect(records.getByText("2 / 2", { exact: true })).toBeVisible();
  const expand = records.getByRole("button", { name: /展开行|Expand row/ });
  if (await expand.count()) await expand.first().click();
  const download = page.waitForEvent("download");
  await records.getByRole("button", { name: "下载箱唛" }).first().click();
  expect((await download).suggestedFilename()).toBe("wfs-label.pdf");
  await page.screenshot({ path: info.outputPath("creation-records.png"), fullPage: true });
  await records.getByRole("button", { name: /^关\s*闭$/ }).last().click();
  await page.reload({ waitUntil: "domcontentloaded" });
  const row = page.getByRole("row").filter({ has: page.getByText(/PK-E2E-MAIN-/, { exact: false }) }).first();
  await expect(row.getByText(/剩余 10 箱/)).toBeVisible();
  await expect(row.getByRole("button", { name: "改装箱" })).toBeDisabled();
  await row.getByRole("button", { name: "创建记录" }).click();
  await expect(page.getByText("程序自动审批通过")).toBeVisible();
});

test("rebox popup retains box editing and tail row; cancel does not mutate", async ({ page }, info) => {
  const row = page.getByRole("row").filter({ has: page.getByText(/PK-E2E-EDIT-/, { exact: false }) }).first();
  await row.getByRole("button", { name: "改装箱" }).click();
  const dialog = page.getByRole("dialog", { name: /改装箱/ });
  await expect(dialog.getByLabel("改装箱原因")).toBeVisible();
  await expect(dialog.getByLabel("单箱毛重（kg）")).toBeVisible();
  await dialog.getByRole("button", { name: "添加箱行" }).click();
  await expect(dialog.getByLabel("第2行箱型")).toBeVisible();
  await page.screenshot({ path: info.outputPath("rebox-popup.png"), fullPage: true });
  await dialog.getByRole("button", { name: /取\s*消|Cancel/ }).click();
  await expect(row.getByText(/3 箱 · 15 件/)).toBeVisible();
});
