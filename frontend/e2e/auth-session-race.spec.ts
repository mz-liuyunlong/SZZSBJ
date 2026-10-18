import { expect, test } from "@playwright/test";

test("ignores a stale logout broadcast after another tab has a newer session", async ({
  context,
}) => {
  const app = await context.newPage();
  const sender = await context.newPage();
  await app.route("**/api/auth/me", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      success: true,
      data: {
        id: 2,
        username: "new-user",
        display_name: "New User",
        is_super_admin: false,
        role_keys: [],
        role_names: [],
        permissions: ["page:products:listing-management:view"],
      },
      error: null,
      meta: null,
      request_id: "synthetic-auth-request",
    }),
  }));
  await app.route("**/api/listings/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const data = path.endsWith("/summary")
      ? {
          total: 0,
          online: 0,
          buybox_exception: 0,
          rating_warning: 0,
          resold_warning: 0,
          strike_price_exception: 0,
        }
      : path.endsWith("/filter-options")
        ? { stores: [], owners: [], product_types: [], tags: [], archive_statuses: [] }
        : path.endsWith("/tags")
          ? { items: [] }
          : { items: [] };
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data,
        error: null,
        meta: { page: 1, page_size: 50, total: 0, latest_calculated_at: null },
        request_id: "synthetic-listing-request",
      }),
    });
  });
  await app.addInitScript(() => {
    localStorage.setItem("szzsbj_auth_token", "new-session-token");
  });

  await app.goto("/#/products/listing-management");
  await expect(app.getByRole("main", { name: "内容区" })).toBeVisible();
  await sender.goto("/#/login");
  await sender.evaluate(() => {
    const channel = new BroadcastChannel("szzsbj_auth_session");
    channel.postMessage({ type: "logged-out", token: "old-session-token" });
    channel.close();
  });

  await expect.poll(() => app.evaluate(() => localStorage.getItem("szzsbj_auth_token")))
    .toBe("new-session-token");
  await expect(app.getByRole("main", { name: "内容区" })).toBeVisible();
});
