// @vitest-environment jsdom
/** Exercise real query/UI contracts with mocked transport; no live database writes. */
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { navigation } from "@/config/navigation";
import PendingPackingPage from "./PendingPackingPage";
import * as api from "./pendingPackingApi";
import * as creation from "./creationApi";
vi.mock("./creationApi", async (original) => ({ ...await original<typeof creation>(), getCreationCapabilities: vi.fn(), createShipments: vi.fn() }));
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
function mount(permissions = ["*"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}><PendingPackingPage page={page} scope="fixture" permissions={permissions} /></QueryClientProvider>);
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(creation.getCreationCapabilities).mockResolvedValue(envelope({ creation_enabled: true, preview_enabled: true, reason: null }));
  window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn(() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} })) });
  vi.mocked(api.listPending).mockResolvedValue(envelope({ items: [row], total: 1 }));
  vi.mocked(api.pendingOptions).mockResolvedValue(envelope({ stores: [{ value: "fixture-store", label: "测试店" }] }));
  vi.mocked(api.pendingSummary).mockResolvedValue(envelope({ completed: 1, ready: 1, test: 1, waiting: 0, no_box: 0, filled_not_done: 0, available_boxes: 2, available_units: 10 }));
});
afterEach(cleanup);

it("covers the page with the shared loading overlay while the list is fetching", async () => {
  let release: (value: ReturnType<typeof envelope<{ items: PendingRow[]; total: number }>>) => void = () => undefined;
  vi.mocked(api.listPending).mockImplementation(() => new Promise((resolve) => { release = resolve; }));
  mount();
  expect(await screen.findByText("正在加载待发货打包单，请稍候")).toBeInTheDocument();
  release(envelope({ items: [], total: 0 }));
  await waitFor(() => expect(screen.queryByText("正在加载待发货打包单，请稍候")).not.toBeInTheDocument());
  expect(screen.getByText("当前条件下暂无已打包完成单据")).toBeInTheDocument();
});

it("opens count-based creation without OWS or a manual approval button and cancels without writes", async () => {
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
  vi.mocked(api.listPending).mockRejectedValue(new Error("offline"));
  mount();
  await screen.findByText(/待发货服务请求失败/);
  expect(screen.queryByText("PK-FIXTURE")).not.toBeInTheDocument();
  expect(screen.getByText("数据加载失败，请重试")).toBeInTheDocument();
});

it("filters on test flag and hides mutations without action permission", async () => {
  mount(["page:pmc:wfs:view"]);
  await screen.findByText("PK-FIXTURE");
  expect(screen.queryByRole("button", { name: "创建 WFS 货件" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: "只看测试单" }));
  await waitFor(() => expect(api.listPending).toHaveBeenLastCalledWith(expect.objectContaining({ only_test: true }), 1, 20, expect.any(AbortSignal)));
});
