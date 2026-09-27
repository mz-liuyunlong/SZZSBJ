// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.setConfig({ testTimeout: 30_000 });
import { navigation } from "@/config/navigation";
import PurchaseBoardPage from "@/pages/pmc/purchase-board/PurchaseBoardPage";
import {
  getPurchaseBoardOwnerOptions,
  getPurchaseBoardSummary,
  getPurchaseOrderDetail,
  listPendingPurchasePlans,
  listPurchaseBoard,
} from "@/pages/pmc/purchase-board/purchaseBoardApi";
import type {
  PurchaseBoardFilters,
  PurchaseBoardRow,
  PurchaseBoardSummary,
} from "@/pages/pmc/purchase-board/purchaseBoardTypes";

vi.mock("@/pages/pmc/purchase-board/purchaseBoardApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/pages/pmc/purchase-board/purchaseBoardApi")>();
  return {
    ...actual,
    listPurchaseBoard: vi.fn(),
    getPurchaseBoardSummary: vi.fn(),
    getPurchaseOrderDetail: vi.fn(),
    listPendingPurchasePlans: vi.fn(),
    getPurchaseBoardOwnerOptions: vi.fn(),
  };
});

interface MockColumn<Row> {
  key: string;
  title: ReactNode;
  render?: (value: unknown, row: Row, index: number) => ReactNode;
}

vi.mock("@ant-design/pro-components", () => ({
  ProTable: <Row extends { id: string }>({
    columns,
    dataSource,
    locale,
    pagination,
  }: {
    columns: MockColumn<Row>[];
    dataSource: Row[];
    locale?: { emptyText?: ReactNode };
    pagination: { current: number; pageSize: number; total: number; onChange: (page: number, pageSize: number) => void };
  }) => (
    <div data-testid="pro-table" data-total={pagination.total}>
      <table>
        <thead><tr>{columns.map((column) => <th key={column.key}>{column.title}</th>)}</tr></thead>
        <tbody>
          {dataSource.map((row, index) => (
            <tr key={row.id} data-testid="board-row">
              {columns.map((column) => (
                <td key={column.key}>{column.render?.(undefined, row, index) ?? null}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {dataSource.length === 0 && locale?.emptyText}
      <button type="button" onClick={() => pagination.onChange(2, pagination.pageSize)}>下一页</button>
      <button type="button" onClick={() => pagination.onChange(1, 200)}>每页200</button>
    </div>
  ),
}));

const page = navigation
  .find((group) => group.key === "pmc")
  ?.children.find((item) => item.key === "pmc_purchase_board");

const row: PurchaseBoardRow = {
  id: "PO1::L1::P1",
  purchaseOrderSn: "PO1",
  orderItemId: "L1",
  planSn: "P1",
  planSns: ["P1"],
  orderStatus: 2,
  stage: {
    stageCode: "S3",
    stageStart: "2026-09-01",
    stageStartEstimated: false,
    thresholdDays: 12,
    dueDate: "2026-09-13",
    overdueDays: 10,
    overdueKind: "arrival",
    alertDueSince: "2026-09-14",
  },
  store: { id: "110652398125259264", name: "Store A", attributed: true },
  sku: "SKU-A",
  productName: "Widget",
  itemId: {
    itemId: "19051502014",
    source: "from_plan_remark",
    sourceRef: "P1",
    matchedAt: "2026-09-23T03:00:00Z",
    matchStatus: "matched",
    msku: "MSKU-A",
    gtin: "00012345678905",
    fulfillmentType: "1",
    wfsNotReady: false,
  },
  owner: { uid: "u-1", name: "Owner One" },
  quantityTotal: 100,
  quantityAllocated: 100,
  quantityReceived: 40,
  progressRatio: 0.4,
  remainingQuantity: 60,
  orderDate: "2026-09-01",
  orderCreateDate: "2026-08-31",
  planCreateDate: "2026-08-29",
  arrivalDate: null,
  arrivalReceiptOrderSn: null,
  purchaseCycleDays: 1,
  approvalCycleDays: 2,
  skuCycle: { valueDays: 12, source: "samples", sampleCount: 5, unstable: true },
  unitPrice: 5,
  amountAllocated: 500,
  amountTotal: 500,
  currencyCode: "CNY",
  calculatedAt: "2026-09-23T03:00:00Z",
};

const summary: PurchaseBoardSummary = {
  awaitingArrivalOrders: 3,
  arrivalOverdueOrders: 1,
  purchaseOverdueOrders: 2,
  purchaseOverduePlans: 4,
  averagePurchaseCycleDays90d: 11.5,
  monthPurchaseAmount: [{ currencyCode: "CNY", amount: 1234 }],
  unstableSkuCount: 1,
  itemidPendingLines: 7,
  wfsNotReadyLines: 0,
  unattributedStoreLines: 2,
  asOf: "2026-09-24",
  meta: { freshnessAt: "2026-09-23T03:00:00Z", ruleVersion: 1, total: null },
};

const lastListFilters = () => {
  const calls = vi.mocked(listPurchaseBoard).mock.calls;
  return calls[calls.length - 1]?.[0] as PurchaseBoardFilters;
};

const renderPage = async () => {
  if (!page) throw new Error("pmc purchase board navigation metadata is required");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <PurchaseBoardPage page={page} preferenceScope="tester" />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(listPurchaseBoard).toHaveBeenCalled());
  await waitFor(() => expect(
    screen.queryByTestId("board-row") ?? screen.queryByRole("alert"),
  ).toBeTruthy());
  return view;
};

beforeEach(() => {
  vi.mocked(listPurchaseBoard).mockResolvedValue({
    rows: [row],
    total: 1,
    meta: { freshnessAt: "2026-09-23T03:00:00Z", ruleVersion: 1, total: 1 },
  });
  vi.mocked(getPurchaseBoardSummary).mockResolvedValue(summary);
  vi.mocked(getPurchaseBoardOwnerOptions).mockResolvedValue([{ uid: "u-1", name: "Owner One", count: 3 }]);
  vi.mocked(listPendingPurchasePlans).mockResolvedValue({
    rows: [{
      planSn: "P3",
      planStatus: 2,
      planCreateDate: "2026-09-10",
      pendingSince: "2026-09-10",
      pendingSinceEstimated: true,
      pendingDays: 14,
      overdueDays: 7,
      store: { id: "s1", name: "Store A", attributed: true },
      sku: "SKU-C",
      productName: "Gadget",
      quantityPlan: 20,
      remarkItemId: null,
    }],
    total: 1,
    thresholdDays: 7,
    meta: { freshnessAt: null, ruleVersion: 1, total: 1 },
  });
  vi.mocked(getPurchaseOrderDetail).mockResolvedValue({
    purchaseOrderSn: "PO1",
    orderStatus: 2,
    orderDate: "2026-09-01",
    orderCreateDate: "2026-08-31",
    quantityTotal: 100,
    quantityReceived: 40,
    progressRatio: 0.4,
    arrivalDate: null,
    amountTotal: 500,
    currencyCode: "CNY",
    stage: row.stage,
    lines: [row],
    receipts: [{ receiptOrderSn: "R1", isArrivalReceipt: false }],
    plans: [{ planSn: "P1", planStatus: 3, planCreateDate: "2026-08-29", quantityPlan: 100, remarkItemId: "19051502014", storeId: "110652398125259264" }],
    skuCycles: [{
      sku: "SKU-A",
      valueDays: 12,
      source: "samples",
      sampleCount: 2,
      baselineDays: null,
      baselineSetOn: null,
      lingxingDefaultDays: 12,
      unstable: true,
      rangeDays: 9,
      samples: [
        { purchaseOrderSn: "PO0", orderDate: "2026-08-01", arrivalDate: "2026-08-13", cycleDays: 12, used: true, exclusion: null },
        { purchaseOrderSn: "PO-1", orderDate: "2026-07-01", arrivalDate: "2026-07-02", cycleDays: 1, used: false, exclusion: "auto_short" },
      ],
      ruleVersion: 1,
      calculatedAt: "2026-09-23T03:00:00Z",
    }],
    meta: { freshnessAt: "2026-09-23T03:00:00Z", ruleVersion: 1, total: null },
  });
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

describe("PurchaseBoardPage", () => {
  it("is registered in navigation under the PMC group with the backend permission key", () => {
    expect(page).toMatchObject({
      key: "pmc_purchase_board",
      path: "/pmc/purchase-board",
      permissionKey: "pmc:purchase:read",
      readOnly: true,
      status: "testing",
    });
  });

  it("renders cards, freshness meta and a board row with the shared Walmart item link", async () => {
    await renderPage();

    expect(screen.getByRole("region", { name: "采购看板" })).toBeInTheDocument();
    expect(await screen.findByText(/数据更新 2026-09-23/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "待到货采购单：3" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "待采购超时：6" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "本月采购金额：¥1,234" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "平均采购交期：11.5 天" })).toBeInTheDocument();

    const tableRow = screen.getByTestId("board-row");
    const link = within(tableRow).getByRole("link", { name: /19051502014/ });
    expect(link).toHaveAttribute("href", "https://www.walmart.com/ip/19051502014");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(tableRow).getByText("已下单未到货")).toBeInTheDocument();
    expect(within(tableRow).getByText("逾期 10 天")).toBeInTheDocument();
    expect(within(tableRow).getByText("已剔除")).toBeInTheDocument();
    expect(within(tableRow).getByText("40 / 100 (40%)")).toBeInTheDocument();
    expect(within(tableRow).getByText("¥500.00")).toBeInTheDocument();
    expect(within(tableRow).getByText("不稳定")).toBeInTheDocument();
  });

  it("maps card clicks to committed filters and toggles them off again", async () => {
    await renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "待到货采购单：3" }));
    await waitFor(() => expect(lastListFilters().statuses).toEqual(["s3", "s4"]));
    expect(lastListFilters().ownerUids).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "ItemID 待处理：7" }));
    await waitFor(() => expect(lastListFilters().itemIdSources).toEqual(["pending_packing_slip", "unresolved"]));
    expect(lastListFilters().statuses).toEqual([]);

    // Clicking the active card again resets the filters; the initial query is served from cache,
    // so assert the pressed state rather than a new request.
    const card = screen.getByRole("button", { name: "ItemID 待处理：7" });
    expect(card).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(card);
    await waitFor(() => expect(card).toHaveAttribute("aria-pressed", "false"));
  });

  it("keeps paging server-side and caps the page size at the backend limit", async () => {
    await renderPage();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(vi.mocked(listPurchaseBoard).mock.calls.at(-1)?.[1]).toBe(2));

    fireEvent.click(screen.getByRole("button", { name: "每页200" }));
    await waitFor(() => expect(vi.mocked(listPurchaseBoard).mock.calls.at(-1)?.[2]).toBe(200));
    expect(vi.mocked(listPurchaseBoard).mock.calls.at(-1)?.[1]).toBe(1);
  });

  it("opens the order detail with lines, receipts, plan chain and excluded cycle samples", async () => {
    await renderPage();

    fireEvent.click(within(screen.getByTestId("board-row")).getByRole("button", { name: "详情" }));
    await waitFor(() => expect(getPurchaseOrderDetail).toHaveBeenCalledWith("PO1", expect.anything()));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("采购单详情 PO1")).toBeInTheDocument();
    expect(within(dialog).getByText("R1")).toBeInTheDocument();
    expect(within(dialog).getByText("19051502014", { selector: "td" })).toBeInTheDocument();
    expect(within(dialog).getByText("PO-1 1 天").tagName).toBe("DEL");
    expect(within(dialog).getByText("PO0 12 天")).toBeInTheDocument();
  });

  it("opens the pending-plan drill-down from the header action", async () => {
    await renderPage();

    fireEvent.click(screen.getByRole("button", { name: "待采购计划" }));
    await waitFor(() => expect(listPendingPurchasePlans).toHaveBeenCalled());
    expect(vi.mocked(listPendingPurchasePlans).mock.calls[0]?.[0]).toMatchObject({ page: 1, pageSize: 50, overdueOnly: false });
    expect(await screen.findByText("P3")).toBeInTheDocument();
    expect(screen.getByText("超时 7 天")).toBeInTheDocument();
    expect(screen.getByText(/超时阈值 7 天/)).toBeInTheDocument();
  });

  it("shows an honest permission message instead of fake data when the API denies access", async () => {
    const denied = Object.assign(new Error("FORBIDDEN"), { status: 403, code: "FORBIDDEN" });
    vi.mocked(listPurchaseBoard).mockRejectedValue(denied);
    vi.mocked(getPurchaseBoardSummary).mockRejectedValue(denied);
    await renderPage();

    expect(await screen.findByText("当前账号没有采购看板查看权限（pmc:purchase:read）。", { selector: ".ant-alert-message" })).toBeInTheDocument();
    expect(screen.getByTestId("pro-table")).toHaveAttribute("data-total", "0");
    expect(screen.queryByTestId("board-row")).not.toBeInTheDocument();
  });
});
