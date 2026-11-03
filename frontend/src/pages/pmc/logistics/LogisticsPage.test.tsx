// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PageHeaderOutletProvider } from "@/components/page/PageShell";
import { navigation } from "@/config/navigation";
import LogisticsPage from "./LogisticsPage";
import * as api from "./logisticsApi";

vi.mock("./logisticsApi");

const page = navigation.find((g) => g.key === "pmc")!.children.find((p) => p.key === "pmc_logistics")!;

const row = (code: string, over: Partial<api.LogisticsRow> = {}): api.LogisticsRow => ({
  code, status: "已发货", created: "2026-10-01", creator: "测试", provider_id: "6995", provider: "众壹物流",
  channel_id: "1", channel: "美东直航", method: "海卡", fc: "ATL1", region: "美东", fee_type: "按计费重",
  tracking: ["ZY1"], cost: { transport: 0, other: 0, currency: "CNY" },
  t: { delivery: "2026-10-01", actual_delivery: "", sail: "", expected_arrival: "", arrival: "", actual_due: "" },
  stores: ["店铺一"], store_id: "s1", goods: [], cargos: [], qty: 10, boxes: 2, gw: 8.5,
  stage: "已开船", done: false, etd: "", atd: "2026-10-05", eta: "", ata: "", pickup: "2026-10-02",
  arrivalPlan: "2026-11-20", arrivalPlanSrc: "atd+voyage+cycle", arrivalActual: "", arrivalActualSrc: "",
  arrivalDate: "2026-11-20", arrivalSrc: "plan", cyc: 12, cycSrc: "real", daysToArrival: 18,
  wmReceiptStart: "", wmFirstReceive: "", wmLastReceipt: "", wmReceiptDone: false, wmActualDelivery: "", wmClosed: "",
  wmSign: "", deliveredCarrier: "", signGap: null, signCheck: "none", sellableDate: "2026-11-30", sellableSrc: "plan",
  daysToSellable: 28, deadline: "2026-11-01", remain: -1, overdue: true, soon: false, usedDays: 31, overdueDays: 1,
  penalty: 15, chargeWeight: 30, ct: 30, missing: [], declared: 10, received: 0,
  ex: [{ type: "已超合同时效", sev: "high", desc: "合同时效 30 天，已超 1 天", since: "2026-11-01" }],
  tr: null, ...over,
});

const ok = <T,>(data: T) => ({ success: true as const, data, error: null, meta: {}, request_id: "r" });

describe("LogisticsPage", () => {
  beforeEach(() => {
    window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} })),
    });
    vi.mocked(api.getBoard).mockResolvedValue(ok({
      today: "2026-11-02",
      rows: [row("SP-OVER"), row("SP-OK", { overdue: false, remain: 5, penalty: 0, ex: [], stage: "已发货" })],
      stages: ["已发货", "已开船"], stage_counts: { 已发货: 1, 已开船: 1 },
      providers: [{ value: "6995", label: "众壹物流" }], channels: [], stores: [{ value: "s1", label: "店铺一" }],
      regions: ["美西", "美中", "美东", "待定"],
      rules: { remind_before: 3, delivered_not_signed: 2, penalty_per_kg_day: 0.5, wm_receive_buffer: 10, receive_diff_buffer: 7, region_total: {} },
      sources: { carrier_tracks: 1, walmart_stores: ["s1"], walmart_batch: "20261102" },
    }) as never);
  });

  it("shows SPs, filters by the overdue card and lists alerts", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <PageHeaderOutletProvider activePageKey={page.key} target={document.body}>
        <QueryClientProvider client={client}>
          <LogisticsPage page={page} scope="test" />
        </QueryClientProvider>
      </PageHeaderOutletProvider>,
    );
    await waitFor(() => expect(screen.getByText("SP-OK")).toBeInTheDocument());
    expect(screen.getByText(/数据日 2026-11-02/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^已超合同时效：/ }));
    await waitFor(() => expect(screen.queryByText("SP-OK")).not.toBeInTheDocument());
    expect(screen.getByText("SP-OVER")).toBeInTheDocument();
    fireEvent.click(screen.getByText("异常与提醒（1）"));
    await waitFor(() => expect(screen.getByText("合同时效 30 天，已超 1 天")).toBeInTheDocument());
  });
});
