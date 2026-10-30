/** Opt-in diagnosis of the user's localhost:5173 frontend against unmocked API reads.
 * Only auth/me is synthetic in a fresh browser context. WFS responses are real 401s;
 * no real credential, login write, business mutation or existing browser session is used.
 */
import { expect, test } from "@playwright/test";

test.use({ channel: process.env.PLAYWRIGHT_CHANNEL ?? "msedge" });
test("localhost:5173 mounts pending packing and emits three real API reads", async ({ page }) => {
  test.skip(process.env.WFS_LIVE_READ_DIAGNOSTIC !== "1", "requires the user's running localhost:5173");
  await page.addInitScript(() => localStorage.setItem("szzsbj_auth_token", "synthetic-read-only-diagnostic"));
  await page.route("**/api/auth/me", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({
      success: true, data: { id: 16, username: "read-diagnostic", is_super_admin: true,
        permissions: ["*"], role_keys: [], role_names: [] },
      error: null, meta: {}, request_id: "synthetic-auth-only",
    }),
  }));
  const paths = ["orders", "summary", "filter-options"].map((suffix) => `/api/pmc/wfs/pending-packing/${suffix}`);
  const responses = paths.map((path) => page.waitForResponse((response) => new URL(response.url()).pathname === path));
  await page.goto("http://localhost:5173/#/pmc/wfs/pending-packing");
  for (const response of await Promise.all(responses)) {
    expect(response.request().method()).toBe("GET");
    expect(response.status()).toBe(401);
    const body = await response.json();
    expect(body.error.code).toBe("UNAUTHORIZED");
    expect(body.request_id).toBeTruthy();
    console.log(`LIVE_READ ${new URL(response.url()).pathname} ${response.status()}`);
  }
  await expect(page.getByText("登录已失效，请重新登录")).toBeVisible();
  const refreshed = paths.map((path) => page.waitForResponse((response) => new URL(response.url()).pathname === path));
  await page.getByRole("button", { name: /刷\s*新/ }).click();
  const refreshedResponses = await Promise.all(refreshed);
  expect(refreshedResponses.map((response) => response.status())).toEqual([401, 401, 401]);
});
