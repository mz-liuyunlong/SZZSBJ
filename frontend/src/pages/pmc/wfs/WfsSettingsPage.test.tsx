// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigation } from "@/config/navigation";
import WfsSettingsPage from "./WfsSettingsPage";
import * as api from "./settingsApi";

vi.mock("./settingsApi", async (orig) => {
  const real = await orig<typeof import("./settingsApi")>();
  return {
    ...real,
    getRules: vi.fn(), listRuleVersions: vi.fn(), listFcRegions: vi.fn(), getCreationDefaults: vi.fn(),
    listLogisticsChannels: vi.fn(), listSettingsChanges: vi.fn(), createRuleVersion: vi.fn(),
  };
});

const pmcPages = navigation.find((g) => g.key === "pmc")!.children;
const pageOf = (key: string) => pmcPages.find((p) => p.key === key)!;
const navPage = pageOf("pmc_wfs_settings");
const row = (node: string, decided: boolean): api.RuleRow => ({
  rule_key: node, node, region: "全部", carrier: "全部", channel: "全部", days: 7, remind_days: 2,
  row_effective_date: "2026-10-10", notify: "PMC", remark: "", decided,
});
const renderPage = (page = navPage, permissions: string[] = []) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <WfsSettingsPage page={page} permissions={permissions} />
    </QueryClientProvider>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn(() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} })),
  });
  vi.mocked(api.getRules).mockResolvedValue({
    version: { version_no: 1, effective_date: "2026-10-10", reason: "8088 初始", created_by: "system:8088-seed", created_at: "2026-10-10T00:00:00Z" },
    rows: [row("货代已签收未收货", true), row("超过预计到仓", false)],
    sample_rows: 1,
  });
  vi.mocked(api.listRuleVersions).mockResolvedValue([]);
  vi.mocked(api.listFcRegions).mockResolvedValue([{
    fc: "LAX1", name: null, zip: "92376", city: "Rialto", state: "CA",
    address: "1 Test Ave, Rialto, CA 92376", region: "美西", region_source: "state", shipments: 3, updated_by: null, updated_at: null,
  }]);
  vi.mocked(api.getCreationDefaults).mockResolvedValue({
    source_account_ref: "acc-1", saved: false, updated_by: null, updated_at: null,
    transport: "LTL", ship_date_offset: 15, pallet_boxes: 16, mixed_boxes: 0, carrier_opt: "own",
  });
  vi.mocked(api.listLogisticsChannels).mockResolvedValue({ items: [], loaded: false });
  vi.mocked(api.listSettingsChanges).mockResolvedValue({ items: [], total: 0 });
});
afterEach(cleanup);

describe("WfsSettingsPage", () => {
  it("rules page shows the rule set with sample rows tagged and paging, without in-page tabs", async () => {
    renderPage();
    expect(await screen.findByText("超过预计到仓")).toBeInTheDocument();
    expect(screen.getAllByText("示例 · 待定")).toHaveLength(1);
    expect(screen.getByText(/有 1 条规则按示例阈值执行/)).toBeInTheDocument();
    expect(screen.getByText("版本 v1 · 生效 2026-10-10")).toBeInTheDocument();
    expect(screen.getByText("共 2 条")).toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(api.listFcRegions).not.toHaveBeenCalled();
  });

  it("FC page shows the zip and the full address", async () => {
    renderPage(pageOf("pmc_wfs_settings_fc"));
    expect(await screen.findByText("LAX1")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "邮编" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "地址全称" })).toBeInTheDocument();
    expect(screen.getByText("92376")).toBeInTheDocument();
    expect(screen.getByText("1 Test Ave, Rialto, CA 92376")).toBeInTheDocument();
    expect(screen.getByText("按州默认")).toBeInTheDocument();
    expect(api.getRules).not.toHaveBeenCalled();
  });

  it("channel page shows the Lingxing channel and provider numbers", async () => {
    vi.mocked(api.listLogisticsChannels).mockResolvedValue({
      loaded: true,
      items: [{ provider_id: "301", provider_name: "某物流商", channel_id: "11918", channel_name: "美西卡派", method_name: "卡派", enabled: true }],
    });
    renderPage(pageOf("pmc_wfs_settings_channels"));
    expect(await screen.findByText("11918")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "渠道编号（领星）" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "物流商编号（领星）" })).toBeInTheDocument();
    expect(screen.getByText("301")).toBeInTheDocument();
    expect(screen.getByText("美西卡派")).toBeInTheDocument();
  });

  it("other section pages render on their own", async () => {
    renderPage(pageOf("pmc_wfs_settings_defaults"));
    expect(await screen.findByText("尚未保存，显示的是 8088 默认值")).toBeInTheDocument();
    cleanup();
    renderPage(pageOf("pmc_wfs_settings_channels"));
    expect(await screen.findByText(/尚未导入物流渠道文件/)).toBeInTheDocument();
    cleanup();
    renderPage(pageOf("pmc_wfs_settings_stores"));
    expect(await screen.findByText(/店铺设置等店铺来源/)).toBeInTheDocument();
    cleanup();
    renderPage(pageOf("pmc_wfs_settings_notes"));
    expect(await screen.findByText(/通知未接入/)).toBeInTheDocument();
    expect(screen.getByText(/上架缓冲天数（10 天）引用「自动补货」/)).toBeInTheDocument();
  });

  it("greys out writes while the page is read-only, even with the manage permission", async () => {
    renderPage(navPage, ["*"]);
    await screen.findByText("超过预计到仓");
    expect(screen.getByRole("button", { name: "编辑规则" })).toBeDisabled();
    expect(screen.getByText(/写入按钮已置灰：本页当前只读/)).toBeInTheDocument();
    cleanup();
    renderPage(pageOf("pmc_wfs_settings_defaults"), ["*"]);
    expect(await screen.findByRole("button", { name: "保存默认值" })).toBeDisabled();
  });

  it("enables editing with the manage permission once the page is writable", async () => {
    renderPage({ ...navPage, readOnly: false }, [api.SETTINGS_MANAGE_PERMISSION]);
    await screen.findByText("超过预计到仓");
    const edit = screen.getByRole("button", { name: "编辑规则" });
    expect(edit).toBeEnabled();
    edit.click();
    expect(await screen.findByRole("button", { name: "+ 新增规则" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存为新版本" })).toBeEnabled();
  });

  it("keeps writes disabled without the manage permission", async () => {
    renderPage({ ...navPage, readOnly: false }, ["page:pmc:wfs:view"]);
    await screen.findByText("超过预计到仓");
    expect(screen.getByRole("button", { name: "编辑规则" })).toBeDisabled();
    expect(screen.getByText(/没有 WFS 设置维护权限/)).toBeInTheDocument();
  });
});
