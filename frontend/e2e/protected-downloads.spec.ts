import { expect, test } from "@playwright/test";

test("downloads authenticated CSV and XLSX responses in a real browser", async ({ page }) => {
  await page.goto("/#/login");
  await page.evaluate(() => {
    localStorage.setItem("szzsbj_auth_token", "synthetic-browser-session");
  });

  await page.route("**/api/e2e-export.csv", (route) => route.fulfill({
    status: 200,
    contentType: "text/csv; charset=utf-8",
    headers: { "Content-Disposition": 'attachment; filename="browser-export.csv"' },
    body: "\ufeffsku,amount\nsynthetic,1\n",
  }));
  await page.route("**/api/e2e-template.xlsx", (route) => route.fulfill({
    status: 200,
    contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    headers: { "Content-Disposition": 'attachment; filename="browser-template.xlsx"' },
    body: "synthetic-xlsx-bytes",
  }));

  const csvDownload = page.waitForEvent("download");
  await page.evaluate(async () => {
    const modulePath = "/src/api/backendApi.ts";
    const { backendDownload } = await import(/* @vite-ignore */ modulePath);
    await backendDownload("/api/e2e-export.csv", "fallback.csv");
  });
  expect((await csvDownload).suggestedFilename()).toBe("browser-export.csv");

  const xlsxDownload = page.waitForEvent("download");
  await page.evaluate(async () => {
    const modulePath = "/src/api/backendApi.ts";
    const { backendDownload } = await import(/* @vite-ignore */ modulePath);
    await backendDownload("/api/e2e-template.xlsx", "fallback.xlsx");
  });
  expect((await xlsxDownload).suggestedFilename()).toBe("browser-template.xlsx");
});
