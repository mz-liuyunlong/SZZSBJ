// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PageHeaderOutletProvider } from "@/components/page/PageShell";
import { navigation } from "@/config/navigation";
import LogisticsPages from "./LogisticsPages";
import * as api from "./logisticsApi";

vi.mock("./logisticsApi", async (orig) => {
  const real = await orig<typeof import("./logisticsApi")>();
  return {
    ...real,
    getOptions: vi.fn(), getOverview: vi.fn(), getAlerts: vi.fn(), getForecast: vi.fn(),
    getCarriers: vi.fn(), getCarrierOrder: vi.fn(), getRules: vi.fn(), getRuleList: vi.fn(), getShippingList: vi.fn(),
  };
});

const pmc = navigation.find((g) => g.key === "pmc")!;
const pageOf = (key: string) => pmc.children.find((p) => p.key === key)
  // 时效与阈值设置 is registered by PMC 设置; render it by key here.
  ?? { ...pmc.children.find((p) => p.key === "pmc_logistics")!, key, title: "时效与阈值设置", path: "/pmc/settings/logistics" };
const ok = <T,>(data: T) => ({ success: true as const, data, error: null, meta: {}, request_id: "r" });

const row = (code: string, over: Partial<api.OverviewRow> = {}): api.OverviewRow => ({
  code, status: "已发货", created: "2026-10-01", creator: "测试", provider_id: "6995", provider: "众壹物流",
  channel_id: "1", channel: "美东直航", method: "海卡", fc: "ATL1", region: "美东", fee_type: "按计费重",
  tracking: ["ZY1"], cost: { transport: 0, other: 0, currency: "CNY" },
  t: { delivery: "2026-10-01", actual_delivery: "", sail: "", expected_arrival: "", arrival: "", actual_due: "" },
  stores: ["店铺一"], store_id: "s1", cargo_count: 1, qty: 10, boxes: 2, gw: 8.5,
  stage: "已开船", done: false, etd: "", atd: "2026-10-05", eta: "", ata: "", pickup: "2026-10-02",
  arrivalPlan: "2026-11-20", arrivalPlanSrc: "atd+voyage+cycle", arrivalActual: "", arrivalActualSrc: "",
  arrivalDate: "2026-11-20", arrivalSrc: "plan", cyc: 12, cycSrc: "real", daysToArrival: 18,
  wmReceiptStart: "", wmFirstReceive: "", wmLastReceipt: "", wmReceiptDone: false, wmActualDelivery: "", wmClosed: "",
  wmSign: "", deliveredCarrier: "", signGap: null, signCheck: "none", sellableDate: "2026-11-30", sellableSrc: "plan",
  daysToSellable: 28, deadline: "2026-11-01", remain: -1, overdue: true, soon: false, usedDays: 31, overdueDays: 1,
  penalty: 15, chargeWeight: 30, ct: 30, missing: [], declared: 10, received: 0,
  ex: [{ type: "已超合同时效", sev: "high", desc: "合同时效 30 天，已超 1 天", since: "2026-11-01" }], ...over,
});

const list = <R, S>(items: R[], summary: S) => ok({ items, total: items.length, page: 1, page_size: 50, summary });

function renderPage(key: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const page = pageOf(key);
  render(
    <PageHeaderOutletProvider activePageKey={page.key} target={document.body}>
      <QueryClientProvider client={client}>
        <LogisticsPages page={page} scope="test" />
      </QueryClientProvider>
    </PageHeaderOutletProvider>,
  );
}

describe("物流 pages", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.clearAllMocks();
    window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} })),
    });
    vi.mocked(api.getOptions).mockResolvedValue(ok({
      today: "2026-11-02", total: 2, stages: ["已发货", "已开船"], stage_counts: { 已发货: 1, 已开船: 1 },
      providers: [{ value: "6995", label: "众壹物流" }], channels: [], stores: [{ value: "s1", label: "店铺一" }],
      regions: ["美西", "美中", "美东", "待定"], owners: ["甲"], carrier_statuses: [{ value: "已开船", label: "已开船（1）" }],
      alert_types: ["已超合同时效"],
      rules: { remind_before: 3, delivered_not_signed: 2, penalty_per_kg_day: 0.5, wm_receive_buffer: 10, receive_diff_buffer: 7, region_total: {} },
      sources: { carrier_orders: 1, walmart_stores: ["s1"], walmart_batch: "20261102" },
    }) as never);
  });

  it("物流总览 pages on the server and sends the card filter", async () => {
    const cards = { all: 2, transit: 2, soon: 0, over: 1, signed: 0, miss: 0, month: 0 };
    vi.mocked(api.getOverview).mockImplementation(async (params) => list(
      params.card === "over" ? [row("SP-OVER")] : [row("SP-OVER"), row("SP-OK", { overdue: false, ex: [], tracking: ["T1", "T2", "T3"] })],
      { cards, shipped: 2, penalty_total: 15, month_start: "2026-11-01", all: 2, qty: 20, boxes: 4 },
    ) as never);
    renderPage("pmc_logistics");
    await waitFor(() => expect(screen.getByText("SP-OK")).toBeInTheDocument());
    expect(screen.getByText(/数据日 2026-11-02/)).toBeInTheDocument();
    expect(vi.mocked(api.getOverview).mock.calls[0][0]).toMatchObject({ page: 1, page_size: 50, card: "all" });
    // 发货单号 / 运单号分两列；多个运单号显示第 1 个 + 省略号，悬停看全部；最后一列「详情」
    expect(screen.getAllByRole("columnheader", { name: "发货单号" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("columnheader", { name: "运单号" }).length).toBeGreaterThan(0);
    expect(screen.getByText("ZY1")).toBeInTheDocument();
    const more = screen.getByLabelText("运单号 3 个");
    expect(more).toHaveTextContent("T1");
    expect(more).not.toHaveTextContent("T2");
    fireEvent.mouseEnter(more);
    await waitFor(() => expect(screen.getByText("T3")).toBeInTheDocument());
    vi.mocked(api.getShippingList).mockReturnValue(new Promise(() => {}) as never);
    fireEvent.click(screen.getAllByText("详情")[0]);
    await waitFor(() => expect(document.querySelector(".ant-drawer-open")).not.toBeNull());
    fireEvent.click(screen.getByRole("button", { name: /^已超合同时效：/ }));
    await waitFor(() => expect(screen.queryByText("SP-OK")).not.toBeInTheDocument());
    expect(vi.mocked(api.getOverview).mock.lastCall?.[0]).toMatchObject({ card: "over", page: 1 });
  });

  it("异常与提醒 lists alerts from the server", async () => {
    vi.mocked(api.getAlerts).mockResolvedValue(list([{
      id: "SP-OVER#已超合同时效#0", type: "已超合同时效", sev: "high", desc: "合同时效 30 天，已超 1 天", since: "2026-11-01",
      code: "SP-OVER", stage: "已开船", provider: "众壹物流", provider_id: "6995", channel: "美东直航", fc: "ATL1", region: "美东", stores: ["店铺一"],
    }], { types: { 已超合同时效: 1 }, sevs: { high: 1, mid: 0, low: 0 }, sps: 1, all: 1 }) as never);
    vi.mocked(api.getRules).mockResolvedValue(ok({
      today: "2026-11-02", thresholds: [{ key: "remind_before", value: 3, unit: "天", label: "即将超时提醒" }],
      region_total: {}, counts: { cycles: 0, contracts: 0, fcs: 0 }, editable: false, edit_hint: "一期只读",
    }) as never);
    renderPage("pmc_logistics_alerts");
    // 业务配置中心版式：头部卡片 + 子页签 + 统计卡 + 异常类型分类 + 列表卡片
    await waitFor(() => expect(screen.getByText("合同时效 30 天，已超 1 天")).toBeInTheDocument());
    expect(screen.getByText("PMC SETTINGS")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "物流 异常与提醒" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /异常清单/ })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "异常类型" })).toBeInTheDocument();
    expect(screen.getByText(/共 1 条 \/ 全部 1 条/)).toBeInTheDocument();
    expect(vi.mocked(api.getAlerts).mock.calls[0][0]).toMatchObject({ page: 1, page_size: 50 });
    // 点异常类型按钮 → 服务端按类型筛选
    fireEvent.click(screen.getByRole("button", { name: /^已超合同时效\s*1$/ }));
    await waitFor(() => expect(vi.mocked(api.getAlerts).mock.lastCall?.[0]).toMatchObject({ type: "已超合同时效", page: 1 }));
    // 提醒规则页签：只读阈值 + 类型口径
    fireEvent.click(screen.getByRole("tab", { name: /提醒规则/ }));
    await waitFor(() => expect(screen.getByText("即将超时提醒")).toBeInTheDocument());
    expect(screen.getByText("无合同时效")).toBeInTheDocument();
  });

  it("到货预测 shows buckets and opens the cargo × SKU lines", async () => {
    const fr: api.ForecastRow = {
      key: "s1|M1", store: "店铺一", store_id: "s1", sku: "SKU-1", msku: "M1", gtin: "G1", name: "碗", item_id: "123", owner: "甲",
      total: 10, bOver: 0, b15: 10, b30: 0, b60: 0, b60p: 0, bNone: 0, signedNP: 0, aShip: 0, aSign: 0, aShelf: 0, anom: 0,
      nextArr: "2026-11-05", nextSell: "2026-11-15", codes: ["SP-1"], cargos: ["C1"], trackings: ["ZY1", "ZY2", "ZY3"],
      lines: [{ code: "SP-1", cargo: "C1", tracking: ["ZY1"], provider: "众壹物流", stage: "已到港", fc: "ATL1", region: "美东", ship: 10, sign: 0, shelf: 0, bucket: "15 天内可售", arr: "2026-11-05", arrSrc: "eta+cycle", arrReal: false, sell: "2026-11-15", sellReal: false, days: 13 }],
    };
    vi.mocked(api.getForecast).mockResolvedValue(list([fr], {
      total: 10, bOver: 0, b15: 10, b30: 0, b60: 0, b60p: 0, bNone: 0, signedNP: 0, aShip: 0, aSign: 0, aShelf: 0, anom: 0,
      products: 1, rows: 1, buffer: 10, region_total: {},
    }) as never);
    renderPage("pmc_logistics_forecast");
    await waitFor(() => expect(screen.getByText("SKU-1")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "123" })).toHaveAttribute("href", "https://www.walmart.com/ip/123");
    // 关联物流：发货单 / 货件 / 运单（多于 2 个折成 +N）
    expect(screen.getByText("SP-1")).toBeInTheDocument();
    expect(screen.getByText("ZY2")).toBeInTheDocument();
    expect(screen.getByText("+1")).toBeInTheDocument();
    expect(vi.mocked(api.getForecast).mock.calls[0][0]).toMatchObject({ field: "sku" });
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "到货预测搜索类型" }));
    fireEvent.click(await screen.findByTitle("运单号"));
    fireEvent.change(screen.getByRole("textbox", { name: "搜索到货预测关键字" }), { target: { value: "ZY1" } });
    fireEvent.keyDown(screen.getByRole("textbox", { name: "搜索到货预测关键字" }), { key: "Enter", code: "Enter" });
    await waitFor(() => expect(vi.mocked(api.getForecast).mock.lastCall?.[0]).toMatchObject({ field: "track", keyword: "ZY1", page: 1 }));
    fireEvent.click(screen.getByText("SKU-1"));
    await waitFor(() => expect(screen.getByText("13 天")).toBeInTheDocument());
    expect(screen.getAllByText("C1").length).toBeGreaterThan(1);
    expect(screen.getByText("众壹物流")).toBeInTheDocument();
    // 点明细里的发货单号：就地展开 / 收起，不再弹第二层抽屉
    vi.mocked(api.getShippingList).mockReturnValue(new Promise(() => {}) as never);
    fireEvent.click(screen.getAllByText("SP-1").at(-1)!);
    await waitFor(() => expect(screen.getByLabelText("发货单 SP-1 详情")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "收起" })).toBeInTheDocument();
    expect(document.querySelectorAll(".ant-drawer-open").length).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: "收起" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "展开" })).toBeInTheDocument());
  });

  it("货代看板 lists carrier orders and the orders that could not be found", async () => {
    vi.mocked(api.getCarriers).mockResolvedValue(list([{
      number: "ZY1", customerNumber: "C1", status: "已开船", provider_id: "6995", provider: "众壹物流", serviceNumber: "", kg: 30, weight: 20, cbm: 1.2,
      sp: "SP-1", sp_status: "已发货", sp_boxes: 2, fc: "ATL1", region: "美东", store_id: "s1", store: "店铺一",
      trackCn: "已开船", trackEn: "", lastTrack: "2026-10-20 08:00", nTracks: 2, staleDays: 13, stale: true,
    }], {
      orders: 1, linked: 1, unlinked: 0, stale: 1, stale_days: 7, queried: 2, zy_sps: 2, status_counts: { 已开船: 1 },
      providers: [{ value: "6995", label: "众壹物流", count: 1 }],
      missing: [{ kind: "查不到", tracking: "ZY9", sp: "SP-9", sp_status: "已发货", store: "店铺一", why: "已校验的众壹文件里没有这张运单" }],
      not_found: 1, no_tracking: 0,
    }) as never);
    renderPage("pmc_logistics_carriers");
    await waitFor(() => expect(screen.getByText("ZY1")).toBeInTheDocument());
    expect(screen.getByText("13 天")).toBeInTheDocument();
    expect(screen.getByText(/没拿到数据的运单 1 张/)).toBeInTheDocument();
    expect(screen.queryByText(/接口调用/)).not.toBeInTheDocument();
    // 物流商列 + 通用标题
    expect(screen.getByRole("columnheader", { name: "物流商" })).toBeInTheDocument();
    expect(screen.getAllByText("众壹物流").length).toBeGreaterThan(0);
    expect(screen.getByText("货代运单（1 / 1 张）")).toBeInTheDocument();
    expect(screen.queryByText(/众壹运单/)).not.toBeInTheDocument();
    // 按发货单号搜索
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "货代运单搜索类型" }));
    fireEvent.click(await screen.findByTitle("发货单号"));
    fireEvent.change(screen.getByRole("textbox", { name: "搜索货代运单关键字" }), { target: { value: "SP-1" } });
    fireEvent.keyDown(screen.getByRole("textbox", { name: "搜索货代运单关键字" }), { key: "Enter", code: "Enter" });
    await waitFor(() => expect(vi.mocked(api.getCarriers).mock.lastCall?.[0]).toMatchObject({ field: "sp", keyword: "SP-1", page: 1 }));
    // 按物流商筛选
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "物流商" }));
    fireEvent.click(await screen.findByTitle("众壹物流（1）"));
    await waitFor(() => expect(vi.mocked(api.getCarriers).mock.lastCall?.[0]).toMatchObject({ provider: "6995", page: 1 }));
  });

  it("时效与阈值设置 is read-only and pages its tables on the server", async () => {
    vi.mocked(api.getRules).mockResolvedValue(ok({
      today: "2026-11-02",
      thresholds: [{ key: "wm_receive_buffer", value: 10, unit: "天", label: "到仓后 Walmart 接收上架缓冲" }],
      region_total: { 美西: 50 }, counts: { cycles: 0, contracts: 1, fcs: 0 }, editable: false, edit_hint: "一期只读",
    }) as never);
    vi.mocked(api.getRuleList).mockImplementation(async (section) => list(
      section === "contracts" ? [{ provider_id: "6995", provider: "众壹物流", channel_id: "1", channel: "美东直航", region: "美东", days: 48, remind: 3, sps: 4 }] : [],
      { all: section === "contracts" ? 1 : 0 },
    ) as never);
    renderPage("pmc_logistics_settings");
    await waitFor(() => expect(screen.getByText("到仓后 Walmart 接收上架缓冲")).toBeInTheDocument());
    expect(screen.getByText(/一期只读/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("48")).toBeInTheDocument());
    expect(vi.mocked(api.getRuleList).mock.calls.map((c) => c[0]).sort()).toEqual(["contracts", "cycles", "fcs"]);
    expect(vi.mocked(api.getRuleList).mock.calls[0][1]).toMatchObject({ page: 1, page_size: 50 });
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });
});
