// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState, type ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AppErrorBoundary from "../components/errors/AppErrorBoundary";
import ErrorFallbackPage from "../pages/errors/ErrorFallbackPage";
import {
  TAB_WORKSPACE_STORAGE_KEY,
  TAB_WORKSPACE_VERSION,
} from "../layouts/useTabWorkspace";
import AppRoutes from "./routes";
import { DEFAULT_BUSINESS_PATH, resolveRoute } from "./routeResolver";

vi.mock("../pages/auth/LoginPage", () => ({
  default: ({ onLogin }: { onLogin: () => void }) => (
    <button type="button" onClick={onLogin}>
      模拟登录
    </button>
  ),
}));

vi.mock("../pages/auth/ForgotPasswordPage", () => ({
  default: () => <h1>模拟忘记密码页</h1>,
}));

vi.mock("../pages/ComingSoonPage", () => ({
  default: ({ page }: { page: { status: string; title: string } }) => (
    <section aria-label="统一占位页">
      <h1 aria-label="当前页面">{page.title}</h1>
      <span aria-label={`页面状态：${page.status}`}>{page.status}</span>
      <span>功能建设中</span>
    </section>
  ),
}));

vi.mock("../layouts/MainLayout", () => ({
  default: function MockMainLayout({
    onLogout,
    renderPage,
  }: {
    onLogout: () => void;
    renderPage: (page: { status: string; title: string }) => ReactNode;
  }) {
    const resolution = resolveRoute(useLocation().pathname);
    return (
      <main aria-label="业务布局">
        <button type="button" onClick={onLogout}>
          模拟退出
        </button>
        {resolution.kind === "allowed" && renderPage(resolution.route.page)}
      </main>
    );
  },
}));

let renderCount = 0;

function ThrowingFixture(): ReactNode {
  renderCount += 1;
  throw new Error(
    "token=secret-token user=private-user env=production stack=internal-stack",
  );
}

beforeEach(() => {
  renderCount = 0;
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

function LocationProbe() {
  return <output aria-label="当前路径">{useLocation().pathname}</output>;
}

function RoutesHarness({ initialLoggedIn }: { initialLoggedIn: boolean }) {
  const [mockLoggedIn, setMockLoggedIn] = useState(initialLoggedIn);
  return (
    <AppRoutes
      mockLoggedIn={mockLoggedIn}
      onLogin={() => setMockLoggedIn(true)}
      onLogout={() => setMockLoggedIn(false)}
    />
  );
}

const renderRoutes = (path: string, initialLoggedIn = false) =>
  render(
    <MemoryRouter initialEntries={[path]} useTransitions={false}>
      <RoutesHarness initialLoggedIn={initialLoggedIn} />
      <LocationProbe />
    </MemoryRouter>,
  );

describe("AppRoutes", () => {
  it("renders login inside the shared auth layout", () => {
    renderRoutes("/login");

    expect(screen.getByRole("button", { name: "模拟登录" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "掌上便捷" })).toBeVisible();
    expect(screen.getByRole("img", { name: "掌上便捷标识" })).toHaveAttribute(
      "src",
      "/favicon.ico",
    );
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/login");
    expect(sessionStorage.getItem(TAB_WORKSPACE_STORAGE_KEY)).toBeNull();
  });

  it("renders forgot-password inside the same auth layout", () => {
    renderRoutes("/forgot-password");

    expect(screen.getByRole("heading", { name: "模拟忘记密码页" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "掌上便捷" })).toBeVisible();
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/forgot-password");
    expect(sessionStorage.getItem(TAB_WORKSPACE_STORAGE_KEY)).toBeNull();
  });

  it("routes a successful mock login to the default business entry", async () => {
    renderRoutes("/login");

    fireEvent.click(screen.getByRole("button", { name: "模拟登录" }));
    await waitFor(() => {
      expect(screen.getByLabelText("当前路径")).toHaveTextContent(DEFAULT_BUSINESS_PATH);
    });
    expect(screen.getByRole("main", { name: "业务布局" })).toBeVisible();
  });

  it("keeps mock auth in memory while restoring the path-only workspace after login", async () => {
    const restoredPath = "/data-center/documentation";
    sessionStorage.setItem(
      TAB_WORKSPACE_STORAGE_KEY,
      JSON.stringify({
        version: TAB_WORKSPACE_VERSION,
        openPaths: [DEFAULT_BUSINESS_PATH, restoredPath],
        activePath: restoredPath,
      }),
    );
    renderRoutes(restoredPath);

    expect(await screen.findByRole("button", { name: "模拟登录" })).toBeVisible();
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/login");

    fireEvent.click(screen.getByRole("button", { name: "模拟登录" }));
    await waitFor(() => {
      expect(screen.getByLabelText("当前路径")).toHaveTextContent(restoredPath);
    });
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      "文档",
    );
  });

  it("redirects unauthenticated business visits to login", async () => {
    renderRoutes("/finance/ad-bill");

    expect(await screen.findByRole("button", { name: "模拟登录" })).toBeVisible();
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/login");
  });

  it("does not restore mock auth in a new runtime", async () => {
    const { unmount } = renderRoutes(DEFAULT_BUSINESS_PATH, true);
    expect(screen.getByRole("main", { name: "业务布局" })).toBeVisible();

    unmount();
    renderRoutes(DEFAULT_BUSINESS_PATH);
    expect(await screen.findByRole("button", { name: "模拟登录" })).toBeVisible();
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/login");
  });

  it("renders the default and hidden business routes when mock logged in", async () => {
    const { unmount } = renderRoutes(DEFAULT_BUSINESS_PATH, true);
    expect(screen.getByRole("main", { name: "业务布局" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      "今日销售",
    );
    expect(screen.getByText("功能建设中")).toBeVisible();

    unmount();
    renderRoutes("/data-center/documentation", true);
    expect(screen.getByRole("main", { name: "业务布局" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      "文档",
    );
    expect(screen.getByLabelText("页面状态：hidden")).toHaveTextContent("hidden");
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/data-center/documentation");
  });

  it("redirects logged-in auth routes to the default business entry", async () => {
    const { unmount } = renderRoutes("/login", true);
    await waitFor(() => {
      expect(screen.getByLabelText("当前路径")).toHaveTextContent(DEFAULT_BUSINESS_PATH);
    });

    unmount();
    renderRoutes("/forgot-password", true);
    await waitFor(() => {
      expect(screen.getByLabelText("当前路径")).toHaveTextContent(DEFAULT_BUSINESS_PATH);
    });
  });

  it("shows a 404 for unknown paths and returns to the default business entry", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderRoutes("/unknown", true);

    expect(screen.getByRole("main", { name: "404错误页面" })).toBeVisible();
    expect(screen.getByText("页面不存在")).toBeVisible();
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/unknown");

    fireEvent.click(screen.getByRole("button", { name: "返回首页" }));

    await waitFor(() =>
      expect(screen.getByLabelText("当前路径")).toHaveTextContent(DEFAULT_BUSINESS_PATH),
    );
    expect(screen.getByRole("main", { name: "业务布局" })).toBeVisible();
    expect(sessionStorage.getItem(TAB_WORKSPACE_STORAGE_KEY)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("AppErrorBoundary", () => {
  it.each(["/login", DEFAULT_BUSINESS_PATH])(
    "shows the same safe fallback for a render error at %s",
    (path) => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      vi.spyOn(console, "error").mockImplementation(() => undefined);
      const view = render(
        <MemoryRouter initialEntries={[path]}>
          <AppErrorBoundary>
            <ThrowingFixture />
          </AppErrorBoundary>
        </MemoryRouter>,
      );

      expect(screen.getByRole("main", { name: "500错误页面" })).toBeVisible();
      expect(screen.getByText("页面暂时无法显示")).toBeVisible();
      expect(document.body).not.toHaveTextContent("secret-token");
      expect(document.body).not.toHaveTextContent("private-user");
      expect(document.body).not.toHaveTextContent("production");
      expect(document.body).not.toHaveTextContent("internal-stack");
      expect(sessionStorage.getItem(TAB_WORKSPACE_STORAGE_KEY)).toBeNull();
      expect(fetchMock).not.toHaveBeenCalled();

      const settledRenderCount = renderCount;
      view.rerender(
        <MemoryRouter initialEntries={[path]}>
          <AppErrorBoundary>
            <ThrowingFixture />
          </AppErrorBoundary>
        </MemoryRouter>,
      );
      expect(renderCount).toBe(settledRenderCount);
    },
  );

  it("returns the 500 fallback to the safe default entry without a request", () => {
    const fetchMock = vi.fn();
    const onReset = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MemoryRouter initialEntries={["/unknown"]}>
        <ErrorFallbackPage onReset={onReset} />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "返回首页" }));

    expect(screen.getByLabelText("当前路径")).toHaveTextContent(DEFAULT_BUSINESS_PATH);
    expect(onReset).toHaveBeenCalledOnce();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
