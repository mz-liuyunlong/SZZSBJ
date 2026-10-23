// @vitest-environment jsdom
/** Exercise real query/UI contracts with mocked transport; no live database writes. */
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { navigation } from "@/config/navigation";
import PendingPackingPage from "./PendingPackingPage";
import * as api from "./pendingPackingApi";
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
  business_test: true, occupied_line_ids: [], available_line_ids: ["00000000-0000-4000-8000-000000000002"], blocked_reasons: [], can_edit: true,
} as unknown as PendingRow;
function mount(permissions = ["*"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}><PendingPackingPage page={page} scope="fixture" permissions={permissions} /></QueryClientProvider>);
}
beforeEach(() => {
  vi.clearAllMocks();
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

it("loads real rows and submits a pending snapshot with stable box selection", async () => {
  vi.mocked(api.submitDrafts).mockResolvedValue(envelope({ drafts: [{ id: "draft", number: "WS-FIXTURE", status: "pending", store_id: "fixture-store", business_test: true, actor_uid: "fixture", created_at: "2026-10-23T00:00:00Z", payload: { items: [] } }] }));
  mount();
  fireEvent.click(await screen.findByRole("checkbox", { name: "选择PK-FIXTURE" }));
  fireEvent.click(screen.getByRole("button", { name: /生成货件草稿/ }));
  fireEvent.change(screen.getByLabelText("退货街道地址"), { target: { value: "Test street" } });
  fireEvent.change(screen.getByLabelText("城市"), { target: { value: "Katy" } });
  fireEvent.change(screen.getByLabelText("州代码"), { target: { value: "TX" } });
  fireEvent.change(screen.getByLabelText("邮编"), { target: { value: "77449" } });
  fireEvent.click(screen.getByRole("button", { name: "保存为待审批草稿" }));
  await screen.findByText(/WS-FIXTURE/);
  expect(api.submitDrafts).toHaveBeenCalledWith(expect.objectContaining({ source_account_ref: "fixture", selections: [expect.objectContaining({ order_id: row.order.id, expected_version: 1, expected_box_version: 1, box_line_ids: row.available_line_ids })] }));
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
  expect(screen.queryByRole("button", { name: /生成货件草稿/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: "只看测试单" }));
  await waitFor(() => expect(api.listPending).toHaveBeenLastCalledWith(expect.objectContaining({ only_test: true }), 1, 20, expect.any(AbortSignal)));
});
