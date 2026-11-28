// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { NavigationPage } from "@/config/navigation";
import SystemConfigPage from "./SystemConfigPage";

vi.mock("@/components/page/PageShell", () => ({ default: ({ children }: { children: ReactNode }) => <section>{children}</section> }));
vi.mock("@/pages/settings/WooCommerceIntegrationPanel", () => ({ default: () => <div>WooCommerce panel test marker</div> }));
beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({ matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() }));
});
afterEach(cleanup);
const page = { key: "settings_system_config", title: "系统配置", tabs: [
  { key: "integrations", title: "平台集成" }, { key: "erp", title: "ERP 集成" },
  { key: "logistics", title: "物流集成" }, { key: "api-policy", title: "接口策略" },
  { key: "parameters", title: "系统参数" },
] } as NavigationPage;

describe("SystemConfigPage", () => {
  it("opens WooCommerce and removes duplicate and obsolete navigation", () => {
    render(<SystemConfigPage page={page} />);
    expect(screen.getByText("WooCommerce panel test marker")).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(5);
    expect(screen.queryByRole("tab", { name: "通知规则" })).not.toBeInTheDocument();
  });
  it("opens ERP field details without offering fake save controls", () => {
    render(<SystemConfigPage page={page} />);
    fireEvent.click(screen.getByRole("tab", { name: /ERP 集成/ }));
    fireEvent.click(screen.getByRole("button", { name: "查看配置项" }));
    expect(screen.getByText("App Secret")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /保存/ })).not.toBeInTheDocument();
  });
  it.each([["物流集成", "物流服务商"], ["接口策略", "请求控制"], ["系统参数", "基础参数"]])("switches to %s", (tab, name) => {
    render(<SystemConfigPage page={page} />);
    fireEvent.click(screen.getByRole("tab", { name: tab }));
    expect(screen.getAllByText(name).length).toBeGreaterThan(0);
  });
  it("previews an interface policy without persisting it", () => {
    render(<SystemConfigPage page={page} />);
    fireEvent.click(screen.getByRole("tab", { name: "接口策略" }));
    fireEvent.click(screen.getByRole("button", { name: "编辑预览" }));
    const input = screen.getByRole("spinbutton", { name: "请求超时" });
    fireEvent.change(input, { target: { value: "45" } });
    fireEvent.click(screen.getByRole("button", { name: "确认预览" }));
    expect((input as HTMLInputElement).value).toBe("45");
    expect(input).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "清除预览" }));
    expect((input as HTMLInputElement).value).toBe("");
    expect(screen.queryByRole("button", { name: /保存/ })).not.toBeInTheDocument();
  });
  it("switches system categories and cancels an edit", () => {
    render(<SystemConfigPage page={page} />);
    fireEvent.click(screen.getByRole("tab", { name: "系统参数" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "文件管理" }));
    fireEvent.click(screen.getByRole("button", { name: "编辑预览" }));
    const input = screen.getByRole("spinbutton", { name: "单次上传大小上限" });
    fireEvent.change(input, { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect((input as HTMLInputElement).value).toBe("");
    expect(input).toBeDisabled();
  });
});
