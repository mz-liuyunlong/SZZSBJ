// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigation } from "@/config/navigation";
import WfsSettingsPage from "./WfsSettingsPage";
import * as api from "./settingsApi";

vi.mock("./settingsApi", async (orig) => {
  const real = await orig<typeof import("./settingsApi")>();
  return {
    ...real,
    getRules: vi.fn(), listRuleRows: vi.fn(), listRuleVersions: vi.fn(), listFcRegions: vi.fn(), getCreationDefaults: vi.fn(),
    listLogisticsChannels: vi.fn(), listSettingsChanges: vi.fn(), createRuleVersion: vi.fn(),
  };
});

const pmcPages = navigation.find((g) => g.key === "pmc")!.children;
const pageOf = (key: string) => pmcPages.find((p) => p.key === key)!;
const rulesPage = pageOf("pmc_wfs_settings");
const version = { version_no: 1, effective_date: "2026-10-10", reason: "8088 初始", created_by: "system:8088-seed", created_at: "2026-10-10T00:00:00Z" };
const row = (node: string, decided: boolean): api.RuleRow => ({
  rule_key: node, node, region: "全部", carrier: "全部", channel: "全部", days: 7, remind_days: 2,
  row_effective_date: "2026-10-10", notify: "PMC", remark: "", decided,
});
const renderPage = (page = rulesPage, permissions: string[] = []) =>
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
  vi.mocked(api.listRuleRows).mockResolvedValue({
    version, items: [row("货代已签收未收货", true), row("超过预计到仓", false)], total: 2, sample_rows: 1, regions: ["全部", "美西"],
  });
  vi.mocked(api.getRules).mockResolvedValue({ version, rows: [row("货代已签收未收货", true)], sample_rows: 0 });
  vi.mocked(api.listRuleVersions).mockResolvedValue([]);
  vi.mocked(api.listFcRegions).mockResolvedValue({
    total: 1, states: ["CA"],
    items: [{
      fc: "LAX1", name: "不应显示的名称", zip: "92376", city: "Rialto", state: "CA",
      address: "1 Test Ave, Rialto, CA 92376", region: "美西", region_source: "state", shipments: 3, updated_by: null, updated_at: null,
    }],
  });
  vi.mocked(api.getCreationDefaults).mockResolvedValue({
    source_account_ref: "acc-1", saved: false, updated_by: null, updated_at: null,
    transport: "LTL", ship_date_offset: 15, pallet_boxes: 16, mixed_boxes: 0, carrier_opt: "own",
  });
  vi.mocked(api.listLogisticsChannels).mockResolvedValue({ items: [], loaded: false, total: 0, providers: [], methods: [] });
  vi.mocked(api.listSettingsChanges).mockResolvedValue({ items: [], total: 0 });
});
afterEach(cleanup);

describe("PMC 设置 · WFS pages", () => {
  it("rules page: title, source, filters, server query, status tags and pagination", async () => {
    renderPage();
    expect(await screen.findByText("超过预计到仓")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "WFS 异常与提醒规则" })).toBeInTheDocument();
    expect(screen.getByText(/版本 v1 · 生效 2026-10-10/)).toBeInTheDocument();
    expect(screen.getByText(/有 1 条规则按示例阈值执行/)).toBeInTheDocument();
    expect(screen.getByText("示例 · 待定")).toBeInTheDocument();
    expect(screen.getByText("已确认")).toBeInTheDocument();
    expect(screen.getByRole("search", { name: "WFS 异常与提醒规则筛选" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "阈值状态" })).toBeInTheDocument();
    expect(screen.getByText("共 2 条")).toBeInTheDocument();
    expect(screen.queryByText("数据来自新系统数据库", { selector: ".ant-alert-message" })).not.toBeInTheDocument();
    expect(api.listRuleRows).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 50, sort_by: "row_no", sort_order: "asc", search_field: "all" }),
      expect.anything(),
    );
    expect(api.getRules).not.toHaveBeenCalled();
  });

  it("rules page sends the committed keyword to the server and resets to page 1", async () => {
    renderPage();
    await screen.findByText("超过预计到仓");
    fireEvent.change(screen.getByLabelText("搜索WFS 异常与提醒规则关键字"), { target: { value: "Dispute" } });
    fireEvent.click(screen.getByRole("button", { name: "搜索WFS 异常与提醒规则" }));
    await waitFor(() => expect(api.listRuleRows).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: "Dispute", page: 1 }), expect.anything(),
    ));
  });

  it("FC page has zip and full address, no name column, and queries the server", async () => {
    renderPage(pageOf("pmc_wfs_settings_fc"));
    expect(await screen.findByText("LAX1")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "邮编" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "地址全称" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "名称" })).not.toBeInTheDocument();
    expect(screen.queryByText("不应显示的名称")).not.toBeInTheDocument();
    expect(screen.getByText("1 Test Ave, Rialto, CA 92376")).toBeInTheDocument();
    expect(screen.getByText("按州默认")).toBeInTheDocument();
    expect(api.listFcRegions).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 50, sort_by: "fc" }), expect.anything());
  });

  it("channel page shows Lingxing numbers and an honest empty state before the file is imported", async () => {
    renderPage(pageOf("pmc_wfs_settings_channels"));
    expect(await screen.findByText("尚未导入物流渠道文件，导入后在这里显示")).toBeInTheDocument();
    cleanup();
    vi.mocked(api.listLogisticsChannels).mockResolvedValue({
      loaded: true, total: 1, providers: ["WFS"], methods: [],
      items: [{ provider_id: "6899", provider_name: "WFS", channel_id: "11918", channel_name: "WFS-FedEx", method_name: null, enabled: true }],
    });
    renderPage(pageOf("pmc_wfs_settings_channels"));
    expect(await screen.findByText("11918")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /渠道编号（领星）/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /物流商编号（领星）/ })).toBeInTheDocument();
    expect(screen.getByText("6899")).toBeInTheDocument();
    expect(screen.getByText("启用")).toBeInTheDocument();
  });

  it("form and notice pages render inside the shared page card", async () => {
    renderPage(pageOf("pmc_wfs_settings_defaults"));
    expect(await screen.findByText("尚未保存，显示的是 8088 默认值")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /保存默认值/ })).toBeDisabled();
    cleanup();
    renderPage(pageOf("pmc_wfs_settings_stores"));
    expect(screen.getByText(/店铺设置等店铺来源/)).toBeInTheDocument();
    cleanup();
    renderPage(pageOf("pmc_wfs_settings_notes"));
    expect(screen.getByText(/通知未接入/)).toBeInTheDocument();
    expect(screen.getByText(/上架缓冲天数（10 天）引用「自动补货」/)).toBeInTheDocument();
  });

  it("greys out writes while the page is read-only, even with the manage permission", async () => {
    renderPage(rulesPage, ["*"]);
    await screen.findByText("超过预计到仓");
    expect(screen.getByRole("button", { name: "编辑规则" })).toBeDisabled();
    expect(screen.getByText("本页当前只读，写入待正式放行")).toBeInTheDocument();
  });

  it("opens the whole-version editor with the manage permission once the page is writable", async () => {
    renderPage({ ...rulesPage, readOnly: false }, [api.SETTINGS_MANAGE_PERMISSION]);
    await screen.findByText("超过预计到仓");
    fireEvent.click(screen.getByRole("button", { name: "编辑规则" }));
    expect(await screen.findByText("编辑规则（保存为新版本）")).toBeInTheDocument();
    await waitFor(() => expect(api.getRules).toHaveBeenCalled());
  });

  it("keeps writes disabled without the manage permission", async () => {
    renderPage({ ...rulesPage, readOnly: false }, ["page:pmc:wfs:view"]);
    await screen.findByText("超过预计到仓");
    expect(screen.getByRole("button", { name: "编辑规则" })).toBeDisabled();
    expect(screen.getByText("没有 PMC 设置维护权限")).toBeInTheDocument();
  });
});
