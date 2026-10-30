// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PageHeaderOutletProvider } from "@/components/page/PageShell";
import { navigation } from "@/config/navigation";
import ShipmentBoardPage from "./ShipmentBoardPage";
import { freshnessText } from "./shipmentBoardFreshness";
import * as api from "./shipmentBoardApi";
import type { BoardFreshness, ShipmentBoardRow } from "./shipmentBoardTypes";

vi.mock("./shipmentBoardApi");

const page = navigation.find((g) => g.key === "pmc")!.children.find((p) => p.key === "pmc_wfs_board")!;
const fresh: BoardFreshness = {
  publication_id: "p1",
  source_observed_at: new Date(Date.now() - 2 * 36e5).toISOString(),
  published_at: new Date().toISOString(),
  coverage_start: "2026-06-01",
  coverage_end: "2026-10-30",
  stale: false,
};
const envelope = <T,>(data: T) => ({ success: true, data, error: null, meta: {}, request_id: "r" });

const lingxingRow: ShipmentBoardRow = {
  id: "lx:p1:900001", source: "lingxing", shipment_id: "3292441WFB", inbound_order_id: "PMC-3292441WFB",
  store_id: "s1", store_name: "CN0001-测试店", status: 2, status_name: "RECEIVING_IN_PROGRESS", status_label: "收货中",
  cargo_sync_status: "已申报", lingxing_sync_status: "SYNCED", business_test: false, its: false, pk: "PK-1",
  sku: "TSKU", product_name: "测试商品", item_id: "1", gtin: "0001", msku: "TSKU-1U", sku_count: 1,
  declared_units: 40, shipped_units: 40, received_units: 38, damaged_units: 2, logistics_code: "LAX2T",
  shipping_codes: ["SP202610160010009"], shipping_status: "已发货", warehouse_id: "16168",
  actual_delivery_date: "2026-10-18", arrival_date: null, expected_arrival_date: "2026-11-05",
  logistics_numbers: ["ZY010009"], created_at: "2026-10-16T07:23:28Z", updated_at: null,
  to_await_at: "2026-10-16T08:00:00Z", to_receive_at: "2026-10-20T00:00:00Z", to_closed_at: null, to_cancelled_at: null,
  operation_id: "o", ticket_id: "t", ticket_number: 1, order_id: "ord", label_state: "READY",
  creation_state: "SUCCEEDED", ticket_state: "SUCCEEDED",
};
const pendingRow: ShipmentBoardRow = {
  ...lingxingRow, id: "cr:t2:WFS-NEW-1", source: "creation_only", shipment_id: "WFS-NEW-1", inbound_order_id: null,
  status: null, status_name: null, status_label: "待领星同步", cargo_sync_status: null, lingxing_sync_status: "PENDING",
  business_test: true, sku_count: 0, declared_units: null, shipped_units: null, received_units: null, damaged_units: null,
  logistics_code: null, shipping_codes: [], shipping_status: null, warehouse_id: null, actual_delivery_date: null,
  expected_arrival_date: null, logistics_numbers: [], to_await_at: null, to_receive_at: null, pk: "PK-2",
};

describe("ShipmentBoardPage", () => {
  beforeEach(() => {
    window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn(() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} })) });
    vi.mocked(api.listShipments).mockResolvedValue(envelope({ items: [lingxingRow, pendingRow], total: 2, data_asof: fresh.source_observed_at!, freshness: fresh }));
    vi.mocked(api.listProducts).mockResolvedValue(envelope({ items: [], total: 0, data_asof: fresh.source_observed_at!, freshness: fresh }));
    vi.mocked(api.shipmentSummary).mockResolvedValue(envelope({ total: 2, by_status: { "2": 1 }, pending_lingxing_sync: 1, test: 1, received_short: 0, freshness: fresh }));
    vi.mocked(api.boardOptions).mockResolvedValue(envelope({ stores: [{ value: "s1", label: "店1" }] }));
  });

  it("renders Lingxing rows with status, quantities and a freshness banner", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <PageHeaderOutletProvider activePageKey={page.key} target={document.body}>
        <QueryClientProvider client={client}>
          <ShipmentBoardPage page={page} scope="test" />
        </QueryClientProvider>
      </PageHeaderOutletProvider>,
    );
    await waitFor(() => expect(screen.getByText("3292441WFB")).toBeInTheDocument());
    expect(screen.getByText(/WFS 货件（2 张）/)).toBeInTheDocument();
    expect(screen.getAllByText("收货中").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("40 / 40")).toBeInTheDocument();
    expect(screen.getByText("38 / 2")).toBeInTheDocument();
    expect(screen.getAllByText("待领星同步").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("status", { name: "领星数据时间" })).toHaveTextContent(/领星数据时间/);
    expect(screen.getByText("PK-2")).toBeInTheDocument();
  });
});

describe("freshnessText", () => {
  it("flags missing or stale publications", () => {
    expect(freshnessText(null)).toEqual({ text: "领星数据尚未同步到看板", stale: true });
    expect(freshnessText({ ...fresh, stale: true }).stale).toBe(true);
    expect(freshnessText(fresh).text).toMatch(/2 小时前/);
    expect(freshnessText(fresh).text).toMatch(/2026-06-01 ～ 2026-10-30/);
  });
});
