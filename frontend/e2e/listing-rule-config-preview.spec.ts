/** Listing rule UI acceptance using local in-memory fixtures only. No backend calls or DB. */
import { expect, test } from "@playwright/test";

test.use({
  channel: process.env.PLAYWRIGHT_CHANNEL,
  viewport: { width: 1440, height: 1000 },
});

async function openPreview(page: import("@playwright/test").Page) {
  const apiRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) {
      apiRequests.push(`${request.method()} ${request.url()}`);
    }
  });
  await page.goto("/?listing-rule-preview=1");
  const drawer = page.getByRole("dialog", { name: "Listing 规则配置" });
  await expect(drawer).toBeVisible();
  await expect(page.getByText("本地前端预览（模拟数据）")).toBeVisible();
  return { drawer, apiRequests };
}

test("four rule groups and protected settings render without database requests", async ({ page }) => {
  const { drawer, apiRequests } = await openPreview(page);

  await expect(drawer.getByText("统计窗口与权重")).toBeVisible();
  await expect(drawer.getByLabel("每日自动计算时间（北京时间）")).toBeVisible();
  await expect(drawer.getByText("默认每天北京时间22:30；保存后在下一次配置时间点生效。", { exact: false })).toBeVisible();
  await drawer.getByRole("tab", { name: "生命周期" }).click();
  await expect(drawer.getByText("上升期增长幅度", { exact: false })).toBeVisible();
  await expect(drawer.getByText("稳定期允许波动", { exact: false })).toBeVisible();

  await drawer.getByRole("tab", { name: "库存与修复" }).click();
  await expect(drawer.getByText("WFS低库存阈值（件）")).toBeVisible();
  await expect(drawer.getByText("长期断货修复有效有货日")).toBeVisible();

  await drawer.getByRole("tab", { name: "运营跟进" }).click();
  await expect(drawer.getByText("每日提醒时间（中国时间）")).toBeVisible();
  await expect(drawer.getByText("启用未来逾期通知（当前不会派发）")).toBeVisible();

  expect(apiRequests).toEqual([]);
});

test("local save creates a mock version, preserves history and never writes through an API", async ({
  page,
}) => {
  const { drawer, apiRequests } = await openPreview(page);
  await drawer.getByRole("spinbutton", { name: "短期统计天数" }).fill("6");
  await drawer.getByRole("textbox", { name: "本次变更原因" }).fill("前端验收模拟修改");
  await drawer.getByRole("button", { name: "保存新版本" }).click();
  await expect(drawer.getByText("v1 待生效")).toBeVisible();
  await drawer.getByRole("tab", { name: "变更记录" }).click();
  await expect(drawer.getByText("前端验收模拟修改")).toBeVisible();
  expect(apiRequests).toEqual([]);
});

test("unsaved changes prompt before closing", async ({ page }) => {
  const { drawer, apiRequests } = await openPreview(page);
  await drawer.getByRole("spinbutton", { name: "短期统计天数" }).fill("6");
  await drawer.getByRole("button", { name: "Close" }).click();
  const confirm = page.getByRole("dialog", { name: "放弃未保存的规则修改？" });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "继续编辑" }).click();
  await expect(drawer).toBeVisible();
  expect(apiRequests).toEqual([]);
});
