// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import AppRoutes from "./routes";
import { DEFAULT_BUSINESS_PATH } from "./routeResolver";

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

vi.mock("../layouts/MainLayout", () => ({
  default: ({ onLogout }: { onLogout: () => void }) => (
    <main aria-label="业务布局">
      <button type="button" onClick={onLogout}>
        模拟退出
      </button>
    </main>
  ),
}));

afterEach(cleanup);

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
  });

  it("renders forgot-password inside the same auth layout", () => {
    renderRoutes("/forgot-password");

    expect(screen.getByRole("heading", { name: "模拟忘记密码页" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "掌上便捷" })).toBeVisible();
    expect(screen.getByLabelText("当前路径")).toHaveTextContent("/forgot-password");
  });

  it("routes a successful mock login to the default business entry", async () => {
    renderRoutes("/login");

    fireEvent.click(screen.getByRole("button", { name: "模拟登录" }));
    await waitFor(() => {
      expect(screen.getByLabelText("当前路径")).toHaveTextContent(DEFAULT_BUSINESS_PATH);
    });
    expect(screen.getByRole("main", { name: "业务布局" })).toBeVisible();
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

    unmount();
    renderRoutes("/data-center/documentation", true);
    expect(screen.getByRole("main", { name: "业务布局" })).toBeVisible();
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

  it("temporarily redirects unknown paths to the default business entry", async () => {
    renderRoutes("/unknown", true);

    await waitFor(() => {
      expect(screen.getByLabelText("当前路径")).toHaveTextContent(DEFAULT_BUSINESS_PATH);
    });
    expect(screen.getByRole("main", { name: "业务布局" })).toBeVisible();
  });
});
