import { expect, test } from "@playwright/test";

test("keeps the session and blocks protected content while auth service is unavailable", async ({
  page,
}) => {
  let profileRequests = 0;
  await page.route("**/api/auth/me", async (route) => {
    profileRequests += 1;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        success: false,
        data: null,
        error: { code: "INTERNAL_ERROR" },
        meta: null,
        request_id: "synthetic-e2e-request",
      }),
    });
  });
  await page.addInitScript(() => {
    localStorage.setItem("szzsbj_auth_token", "synthetic-e2e-session");
  });

  await page.goto("http://127.0.0.1:4173/#/products/listing-management");

  await expect(page.getByText("暂时无法验证登录状态")).toBeVisible();
  await expect(page.getByRole("main", { name: "内容区" })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("szzsbj_auth_token")))
    .toBe("synthetic-e2e-session");

  await page.getByRole("button", { name: /重\s*试/ }).click();
  await expect.poll(() => profileRequests).toBe(2);
  await expect.poll(() => page.evaluate(() => localStorage.getItem("szzsbj_auth_token")))
    .toBe("synthetic-e2e-session");
});
