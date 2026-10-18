import { expect, test } from "@playwright/test";

const authEnvelope = (data: unknown) => JSON.stringify({
  success: true,
  data,
  error: null,
  meta: null,
  request_id: "synthetic-auth-request",
});

const backendUser = (id: number, username: string, displayName: string) => ({
  id,
  username,
  display_name: displayName,
  phone: null,
  email: null,
  is_active: true,
  is_super_admin: false,
  role_keys: [],
  role_names: [],
  permissions: ["page:products:listing-management:view"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  last_login_at: null,
});

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

test("keeps user B signed in when user A's delayed logout completes", async ({ context }) => {
  const app = await context.newPage();
  let finishOldLogout: (() => Promise<void>) | undefined;
  let markLogoutReceived: (() => void) | undefined;
  const logoutReceived = new Promise<void>((resolve) => {
    markLogoutReceived = resolve;
  });

  await context.route("**/api/auth/login", async (route) => {
    const body = route.request().postDataJSON() as { username: string };
    const isUserB = body.username === "user-b";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: authEnvelope({
        access_token: isUserB ? "session-b" : "session-a",
        token_type: "bearer",
        expires_at: "2030-01-01T00:00:00Z",
        user: backendUser(isUserB ? 2 : 1, body.username, isUserB ? "User B" : "User A"),
      }),
    });
  });
  await context.route("**/api/auth/me", async (route) => {
    const token = route.request().headers().authorization;
    const isUserB = token === "Bearer session-b";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: authEnvelope(backendUser(
        isUserB ? 2 : 1,
        isUserB ? "user-b" : "user-a",
        isUserB ? "User B" : "User A",
      )),
    });
  });
  await context.route("**/api/auth/logout", async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer session-a");
    finishOldLogout = () => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: authEnvelope({ revoked: true }),
    });
    markLogoutReceived?.();
  });
  await context.route("**/api/listings/**", async (route) => {
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
    await route.fulfill({
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

  await app.goto("/#/login");
  await app.getByPlaceholder("请输入账号").fill("user-a");
  await app.getByPlaceholder("请输入密码").fill("synthetic-password");
  await app.getByRole("button", { name: "登录" }).click();
  await expect(app.getByRole("main", { name: "内容区" })).toBeVisible();

  await app.getByRole("button", { name: "用户菜单" }).hover();
  await app.getByRole("menuitem", { name: "退出" }).click();
  await app.getByRole("button", { name: "退出登录", exact: true }).click();
  await logoutReceived;
  await expect(app.getByRole("main", { name: "内容区" })).toHaveCount(0);
  await expect(app.getByRole("button", { name: "登录" })).toBeVisible();

  await app.getByPlaceholder("请输入账号").fill("user-b");
  await app.getByPlaceholder("请输入密码").fill("synthetic-password");
  await app.getByRole("button", { name: "登录" }).click();
  await expect(app.getByRole("main", { name: "内容区" })).toBeVisible();
  await expect.poll(() => app.evaluate(() => localStorage.getItem("szzsbj_auth_token")))
    .toBe("session-b");

  expect(finishOldLogout).toBeDefined();
  await finishOldLogout!();
  await expect.poll(() => app.evaluate(() => localStorage.getItem("szzsbj_auth_token")))
    .toBe("session-b");
  await app.getByRole("button", { name: "用户菜单" }).hover();
  await expect(app.getByText("User B")).toBeVisible();
  await expect(app.getByRole("main", { name: "内容区" })).toBeVisible();

  const sender = await context.newPage();
  await sender.goto("/#/login");
  await sender.evaluate(() => {
    const channel = new BroadcastChannel("szzsbj_auth_session");
    channel.postMessage({ type: "logged-out", token: "session-a" });
    channel.close();
  });
  await expect.poll(() => app.evaluate(() => localStorage.getItem("szzsbj_auth_token")))
    .toBe("session-b");
  await expect(app.getByText("User B")).toBeVisible();
  await expect(app.getByRole("main", { name: "内容区" })).toBeVisible();
});
