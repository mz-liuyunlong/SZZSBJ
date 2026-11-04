// @vitest-environment jsdom
/** Exercise real query/UI contracts with mocked transport; no live database writes. */
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { navigation } from "@/config/navigation";
import PendingPackingPage from "./PendingPackingPage";
import * as api from "./pendingPackingApi";
import * as creation from "./creationApi";
vi.mock("./creationApi", async (original) => ({ ...await original<typeof creation>(), getCreationCapabilities: vi.fn(), createShipments: vi.fn(), getCreationDefaults: vi.fn(), getTicketCounts: vi.fn(), listCreationTickets: vi.fn(), retryCreation: vi.fn(), listStoreDefaults: vi.fn(), saveStoreDefaults: vi.fn(), listBoardRows: vi.fn(), printCreationLabel: vi.fn(), simulatorPull: vi.fn() }));
import type { PendingRow } from "./pendingPackingTypes";

vi.mock("./pendingPackingApi", async (original) => ({ ...await original<typeof api>(), listPending: vi.fn(), pendingOptions: vi.fn(), pendingSummary: vi.fn(), submitDrafts: vi.fn() }));
const envelope = <T,>(data: T) => ({ success: true, data, error: null, meta: {}, request_id: "fixture" });
const page = navigation.find((g) => g.key === "pmc")!.children.find((p) => p.key === "pmc_wfs_pending_packing")!;
const row = {
  order: { id: "00000000-0000-4000-8000-000000000001", source_account_ref: "fixture", version: 1,
    pk: "PK-FIXTURE", sku: "TEST-SKU", store_id: "fixture-store", store_name: "测试店", item_id: "123456",
    gtin: "00000000000001", product_name: "测试商品", approved_quantity: 10, customs_value: false,
    box_set: { id: "box", version: 1, total_qty: 10, completed_at: "2026-10-23T00:00:00Z", completed_by: "仓库",
      lines: [{ id: "00000000-0000-4000-8000-000000000002", line_no: 1, boxes: 2, units_per_box: 5 }] } },
  total_boxes: 2, occupied_boxes: 0, available_boxes: 2, available_units: 10, business_test: true, occupied_line_ids: [], available_line_ids: ["00000000-0000-4000-8000-000000000002"], blocked_reasons: [], can_edit: true,
} as unknown as PendingRow;
const ticket = (tab: creation.TicketTab): creation.TicketRow => ({
  operation_id: "op-1", order_id: row.order.id, ticket_id: `t-${tab}`, number: 1, tab, inbound_order_id: tab === "created" ? "PMC-HK2614-20261104-01" : null,
  state: tab === "failed" ? "FAILED" : tab === "created" ? "SUCCEEDED" : "RUNNING",
  status_label: { submitting: "提交中 · 已查询 2/10 次", failed: "Walmart 拒绝", created: "已创建未发货" }[tab],
  pks: ["PK-FIXTURE"], skus: ["TEST-SKU"], store_id: "fixture-store", store_name: "测试店", source_account_ref: "fixture",
  boxes: 2, units: 10, error_code: tab === "failed" ? "WFS_PLATFORM_REJECTED" : null,
  error_message: tab === "failed" ? "Invalid returnAddress.postalCode" : null, submissions: 1,
  polls: tab === "submitting" ? 2 : null, max_polls: tab === "submitting" ? 10 : null, next_poll_at: null,
  shipments: tab === "created" ? [{ shipment_id: "SHIP-1", label_state: "READY", fc: "ATL1" }] : [],
  expected_delivery_at: "2026-11-13T00:00:00+08:00", created_at: "2026-11-04T01:00:00Z", created_by: "16",
  approved_at: "2026-11-04T01:05:00Z", approved_by: "rocky", approval_ref: "rocky-written:1", awaiting_approval: false,
});
const boardCounts = { pending: 1, submitting: 1, failed: 1, created: 1, shipped: 1 };
const pendingBoard = (): creation.BoardRow => ({
  key: `pending:${row.order.id}`, kind: "pending", status: "pending", status_label: "待创建", detail: "可建 2 箱 / 10 件",
  sort_at: "2026-10-23T00:00:00Z", order_id: row.order.id, pk: "PK-FIXTURE", store_id: "fixture-store", store_name: "测试店",
  sku: "TEST-SKU", product_name: "测试商品", item_id: "123456", gtin: "00000000000001", business_test: true,
  pending: row, ticket: null, shipment_id: null, fc: null, label_state: null, print_count: 0, printed_at: null, printed_by: null, shipping_code: null, demo: false,
});
const shipmentBoard = (tab: creation.TicketTab, extra: Partial<creation.BoardRow> = {}): creation.BoardRow => ({
  ...pendingBoard(), key: `ticket:${tab}`, kind: "shipment", pending: null, ticket: ticket(tab),
  status: tab, status_label: { submitting: "提交中", failed: "创建失败", created: "已创建未发货" }[tab],
  detail: { submitting: "提交中 · 已查询 2/10 次", failed: "Invalid returnAddress.postalCode", created: null }[tab],
  shipment_id: tab === "created" ? "SHIP-1" : null, fc: tab === "created" ? "ATL1" : null, label_state: tab === "created" ? "READY" : null,
  ...extra,
});
const boardItems = () => [pendingBoard(), shipmentBoard("submitting"), shipmentBoard("failed"), shipmentBoard("created", { print_count: 2, printed_by: "rocky" })];
function mount(permissions = ["*"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}><PendingPackingPage page={page} scope="fixture" permissions={permissions} /></QueryClientProvider>);
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(creation.getCreationCapabilities).mockResolvedValue(envelope({ creation_enabled: true, preview_enabled: true, reason: null }));
  window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn(() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} })) });
  vi.mocked(creation.getCreationDefaults).mockResolvedValue(envelope({ source_account_ref: "fixture", store_id: "fixture-store", transport: "LTL", ship_date_offset: 9, pallet_boxes: 16, mixed_boxes: 0, carrier_opt: "own", its: true, return_address: { address_line1: "1 Store St", city: "Katy", state_code: "TX", postal_code: "77449", country_code: "US" }, saved: true, level: "store", expected_delivery_date: "2026-11-13" }));
  vi.mocked(creation.getTicketCounts).mockResolvedValue(envelope({ submitting: 1, failed: 1, created: 1 }));
  vi.mocked(creation.listCreationTickets).mockImplementation((tab) => Promise.resolve(envelope({ items: [ticket(tab)], total: 1 })));
  vi.mocked(creation.retryCreation).mockResolvedValue(envelope({} as creation.CreationOperation));
  const defaultsRow = { source_account_ref: "fixture", transport: "LTL" as const, ship_date_offset: 15, pallet_boxes: 16, mixed_boxes: 0, carrier_opt: "own" as const, its: true, return_address: { address_line1: "14125 TELEPHONE AVE", city: "CHINO", state_code: "CA", postal_code: "91710", country_code: "US" as const }, updated_by: "rocky", updated_at: "2026-11-04T08:00:00Z" };
  vi.mocked(creation.listStoreDefaults).mockResolvedValue(envelope({
    common: [{ ...defaultsRow, store_id: "*", store_name: "全部店铺通用", level: "common" }],
    items: [{ ...defaultsRow, store_id: "fixture-store", store_name: "测试店", level: "common", updated_by: null, updated_at: null }],
  }));
  vi.mocked(creation.saveStoreDefaults).mockResolvedValue(envelope({} as creation.StoreDefaultsRow));
  vi.mocked(creation.listBoardRows).mockResolvedValue(envelope({ items: boardItems(), total: 4, counts: boardCounts }));
  vi.mocked(creation.printCreationLabel).mockResolvedValue(undefined);
  vi.mocked(creation.simulatorPull).mockResolvedValue(envelope({ run_ids: ["run-1"] }));
  vi.mocked(api.listPending).mockResolvedValue(envelope({ items: [row], total: 1 }));
  vi.mocked(api.pendingOptions).mockResolvedValue(envelope({ stores: [{ value: "fixture-store", label: "测试店" }] }));
  vi.mocked(api.pendingSummary).mockResolvedValue(envelope({ completed: 1, ready: 1, test: 1, waiting: 0, no_box: 0, filled_not_done: 0, available_boxes: 2, available_units: 10 }));
});
afterEach(cleanup);

it("covers the page with the shared loading overlay while the list is fetching", async () => {
  let release: (value: ReturnType<typeof envelope<{ items: creation.BoardRow[]; total: number; counts: creation.BoardRowCounts }>>) => void = () => undefined;
  vi.mocked(creation.listBoardRows).mockImplementation(() => new Promise((resolve) => { release = resolve; }));
  mount();
  expect(await screen.findByText("正在加载待创建货件，请稍候")).toBeInTheDocument();
  release(envelope({ items: [], total: 0, counts: { ...boardCounts, pending: 0 } }));
  await waitFor(() => expect(screen.queryByText("正在加载待创建货件，请稍候")).not.toBeInTheDocument());
  expect(screen.getByText("当前条件下没有货件")).toBeInTheDocument();
});

it("opens count-based creation without OWS or an approval step and cancels without writes", async () => {
  mount();
  fireEvent.click(await screen.findByRole("checkbox", { name: "选择PK-FIXTURE" }));
  fireEvent.click(screen.getByRole("button", { name: "创建 WFS 货件" }));
  expect(await screen.findByRole("spinbutton", { name: "本次发货箱数" })).toHaveValue("2");
  expect(screen.queryByLabelText("OWS")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^(提交审批|批准|驳回)$/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /^取\s*消$/ }));
  expect(creation.createShipments).not.toHaveBeenCalled();
});

it("keeps errors visible and never replaces failed reads with samples", async () => {
  vi.mocked(creation.listBoardRows).mockRejectedValue(new Error("offline"));
  mount();
  expect((await screen.findAllByText(/待发货服务请求失败/)).length).toBeGreaterThan(0);
  expect(screen.queryByText("PK-FIXTURE")).not.toBeInTheDocument();
});

it("filters on test flag and hides mutations without action permission", async () => {
  mount(["page:pmc:wfs:view"]);
  await screen.findAllByText("PK-FIXTURE");
  expect(screen.queryByRole("button", { name: "创建 WFS 货件" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "重试" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: "只看测试单" }));
  await waitFor(() => expect(creation.listBoardRows).toHaveBeenLastCalledWith(expect.objectContaining({ only_test: true }), 1, 50, expect.any(AbortSignal)));
});

it("is one list: a status on every row, the PK repeats, shipped hidden by default, no tabs or help button", async () => {
  mount();
  expect((await screen.findAllByText("PK-FIXTURE")).length).toBe(4);
  expect(creation.listBoardRows).toHaveBeenCalledWith(expect.objectContaining({ statuses: ["pending", "submitting", "failed", "created"], show_shipped: false }), 1, 50, expect.any(AbortSignal));
  expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  expect(screen.queryByText("待批准")).not.toBeInTheDocument();
  for (const text of ["提交中 · 已查询 2/10 次", "Invalid returnAddress.postalCode", "SHIP-1", "ATL1", "PMC-HK2614-20261104-01", "已打印（2 次） · rocky"]) expect(screen.getByText(text)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /帮助/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /帮助/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("switch", { name: "显示已发货" }));
  await waitFor(() => expect(creation.listBoardRows).toHaveBeenLastCalledWith(expect.objectContaining({ show_shipped: true }), 1, 50, expect.any(AbortSignal)));
  fireEvent.click(screen.getByRole("button", { name: /创建失败/ }));
  await waitFor(() => expect(creation.listBoardRows).toHaveBeenLastCalledWith(expect.objectContaining({ statuses: ["failed"] }), 1, 50, expect.any(AbortSignal)));
});

it("prints only created rows' labels and retries a failed row", async () => {
  mount();
  await screen.findAllByText("PK-FIXTURE");
  const prints = screen.getAllByRole("button", { name: "打印箱唛" });
  expect(prints).toHaveLength(3);  // 提交中 / 创建失败 / 已创建
  expect(prints.filter((b) => !(b as HTMLButtonElement).disabled)).toHaveLength(1);
  fireEvent.click(prints.find((b) => !(b as HTMLButtonElement).disabled)!);
  await waitFor(() => expect(creation.printCreationLabel).toHaveBeenCalledWith("op-1", "SHIP-1"));
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  fireEvent.click(await screen.findByRole("button", { name: "确认重试" }));
  await waitFor(() => expect(creation.retryCreation).toHaveBeenCalledWith("op-1"));
});

it("shows the simulator banner and 立即拉取结果 only in local simulator mode", async () => {
  mount();
  await screen.findAllByText("PK-FIXTURE");
  expect(screen.queryByText(/本机模拟通道，不连 Walmart/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /立即拉取结果/ })).not.toBeInTheDocument();
  cleanup();
  vi.mocked(creation.getCreationCapabilities).mockResolvedValue(envelope({ creation_enabled: true, preview_enabled: true, reason: null, mode: "simulator", simulator: true }));
  mount();
  expect(await screen.findByText(/本机模拟通道，不连 Walmart/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /立即拉取结果/ }));
  await waitFor(() => expect(creation.simulatorPull).toHaveBeenCalled());
});

it("prefills the creation dialog from the store's defaults without saving them", async () => {
  mount();
  fireEvent.click(await screen.findByRole("checkbox", { name: "选择PK-FIXTURE" }));
  fireEvent.click(screen.getByRole("button", { name: "创建 WFS 货件" }));
  expect(await screen.findByDisplayValue("1 Store St")).toBeInTheDocument();
  expect(screen.getByDisplayValue("2026-11-13")).toBeInTheDocument();
  expect(screen.getByText(/本店铺的创建默认值/)).toBeInTheDocument();
  expect(creation.getCreationDefaults).toHaveBeenCalledWith("fixture", "fixture-store", expect.any(AbortSignal));
  expect(creation.saveStoreDefaults).not.toHaveBeenCalled();
});

it("opens 创建默认值 in a side drawer: 全部店铺通用 first, stores below fall back to it", async () => {
  mount();
  fireEvent.click(await screen.findByRole("button", { name: /创建默认值/ }));
  expect(await screen.findByText("全部店铺通用")).toBeInTheDocument();
  const drawer = screen.getByText("全部店铺通用").closest(".ant-drawer") as HTMLElement;
  const rows = within(drawer).getAllByRole("row").filter((r) => r.querySelector("td"));
  expect(within(rows[0]).getByText("全部店铺通用")).toBeInTheDocument();
  expect(within(rows[0]).getByText("已设置")).toBeInTheDocument();
  expect(within(rows[1]).getByText("测试店")).toBeInTheDocument();
  expect(within(rows[1]).getByText("沿用通用")).toBeInTheDocument();
  fireEvent.click(within(rows[0]).getByRole("button", { name: "编辑" }));
  expect(await screen.findByText("编辑创建默认值 · 全部店铺通用")).toBeInTheDocument();
  fireEvent.click(await screen.findByRole("button", { name: /保\s*存/ }));
  await waitFor(() => expect(creation.saveStoreDefaults).toHaveBeenCalledWith("*", expect.objectContaining({ transport: "LTL", ship_date_offset: 15, source_account_ref: "fixture", return_address: expect.objectContaining({ city: "CHINO" }) })));
});
