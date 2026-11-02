// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BusinessConfigPage from "./BusinessConfigPage";
import type { NavigationPage } from "@/config/navigation";

const mocks = vi.hoisted(() => ({
  fetchConfig: vi.fn(),
  fetchUsage: vi.fn(),
  saveConfig: vi.fn(),
  currentUser: vi.fn(),
}));

vi.mock("@/api/decodoApi", () => ({
  fetchDecodoConfig: mocks.fetchConfig,
  fetchDecodoUsage: mocks.fetchUsage,
  updateDecodoConfig: mocks.saveConfig,
}));
vi.mock("@/pages/auth/authApi", () => ({
  fetchCurrentUser: mocks.currentUser,
}));
vi.mock("@/components/page/PageShell", () => ({
  default: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
}));

const page = { key: "settings_business_config", title: "业务配置" } as NavigationPage;
const config = {
  configured: true,
  enabled: true,
  us_zip: "10001",
  updated_at: null,
  updated_by: null,
  mode: "database" as const,
};
const day = {
  date: "2026-10-25",
  amazon_requests: 3,
  walmart_requests: 2,
  total: 5,
  success: 4,
  failed: 1,
  pending: 0,
};

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  mocks.fetchConfig.mockReset().mockResolvedValue(config);
  mocks.fetchUsage.mockReset().mockResolvedValue({
    timezone: "America/New_York",
    today: "2026-10-25",
    days: [day],
  });
  mocks.saveConfig.mockReset().mockResolvedValue(config);
  mocks.currentUser.mockReset().mockResolvedValue({ isSuperAdmin: true });
});
afterEach(cleanup);

describe("business configuration V2", () => {
  it("renders real Decodo data, and filters empty categories", async () => {
    render(<BusinessConfigPage page={page} />);
    expect(await screen.findByText("Decodo Scraper API")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /群机器人与通知/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /云存储与文件/ })).not.toBeInTheDocument();
    expect(screen.getAllByText("未配置计价").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /AI 服务/ }));
    expect(screen.queryByText("Decodo Scraper API")).not.toBeInTheDocument();
    expect(screen.getByText("该分类暂无服务配置")).toBeInTheDocument();
    expect(mocks.fetchConfig).toHaveBeenCalledTimes(1);
  });

  it("restores search, status filter and view control without removing services", async () => {
    render(<BusinessConfigPage page={page} />);
    expect(await screen.findByText("Decodo Scraper API")).toBeInTheDocument();
    const search = screen.getByRole("searchbox", { name: "搜索服务配置" });
    fireEvent.change(search, { target: { value: "no-matching-service" } });
    expect(screen.queryByText("Decodo Scraper API")).not.toBeInTheDocument();
    expect(screen.getByText("该分类暂无服务配置")).toBeInTheDocument();
    fireEvent.change(search, { target: { value: "Decodo" } });
    expect(screen.getByText("Decodo Scraper API")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "状态筛选" })).toBeInTheDocument();
    expect(screen.getByLabelText("服务视图切换")).toBeInTheDocument();
  });

  it("does not expose edit actions to a read-only user", async () => {
    mocks.currentUser.mockResolvedValue({ isSuperAdmin: false });
    render(<BusinessConfigPage page={page} />);
    expect(await screen.findByText("Decodo Scraper API")).toBeInTheDocument();
    await waitFor(() => expect(mocks.currentUser).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "新增服务配置" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
  });

  it("uses the requested 30-day window in the real usage API", async () => {
    render(<BusinessConfigPage page={page} />);
    fireEvent.click(screen.getByRole("tab", { name: /用量与费用/ }));
    fireEvent.click(screen.getByText("最近 30 天"));
    await waitFor(() => expect(mocks.fetchUsage).toHaveBeenCalledWith(30));
    expect(screen.getByText("尚未配置计价规则")).toBeInTheDocument();
  });

  it("keeps edit actions hidden in local test mode", async () => {
    mocks.fetchConfig.mockResolvedValue({ ...config, mode: "local_test" });
    render(<BusinessConfigPage page={page} />);
    expect(await screen.findByText("Decodo Scraper API")).toBeInTheDocument();
    expect(screen.getByText(/Decodo 处于本地 SQLite 测试模式/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
  });
});
