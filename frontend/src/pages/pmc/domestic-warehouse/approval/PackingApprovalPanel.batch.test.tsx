// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { decidePacking, type ApprovalCandidate, type PackingOrder } from "./packingApprovalApi";
import PackingApprovalPanel from "./PackingApprovalPanel";

const refresh = vi.fn().mockResolvedValue(undefined);
const rows: ApprovalCandidate[] = [];

vi.mock("./packingApprovalApi", async () => {
  const actual = await vi.importActual<typeof import("./packingApprovalApi")>("./packingApprovalApi");
  return { ...actual, decidePacking: vi.fn() };
});
vi.mock("./packingApprovalQueries", () => ({
  usePackingApproval: () => ({
    list: { data: { data: { items: rows, total: rows.length } }, error: null, isFetching: false },
    summary: { data: { data: { pending: rows.length, overdue: 0, blocked: 1, approved: 0, rejected: 0 } }, error: null },
    options: { data: { data: { stores: [] } }, error: null, isFetching: false },
    history: { data: undefined, error: null, isFetching: false, refetch: vi.fn() },
    user: { data: { permissions: ["*"] }, error: null },
    decision: { isPending: false, mutateAsync: vi.fn() },
    refresh,
  }),
}));

function candidate(id: string, overrides: Partial<ApprovalCandidate> = {}): ApprovalCandidate {
  return {
    id, candidate_version: `v-${id}`, source_account_ref: "primary", warehouse_id: "16168", warehouse_name: "美中1号仓TX", publication_id: "p", board_id: "b",
    inbound_order_sn: `IB-${id}`, sku: "YC00236", product_name: null, store_id: "1", store_name: "HK2614", item_id: "20394207859",
    gtin: "00000000000000", msku: "YC00236-1A", purchase_order_sns: [], draft_nos: [], arrival_purchased: null, arrival_received: null,
    arrival_pending: null, arrival_status: "unknown", candidate_created_on: "2026-10-06", overdue: false, stock_balance: 10,
    available_quantity: 10, default_quantity: 10, can_approve: true, blocked_reasons: [], source_observed_at: "2026-10-06T00:00:00Z",
    ...overrides,
  };
}
const order = (pk: string, splitPks?: string[]) => ({ success: true, data: { pk, split_pks: splitPks } as PackingOrder, error: null, meta: {}, request_id: "t" }) as unknown as Awaited<ReturnType<typeof decidePacking>>;

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
  rows.splice(0, rows.length,
    candidate("a"),
    candidate("b", { default_quantity: 6, manual_customs: "declare", split_lines: [
      { store_id: "1", store_name: "HK2614", item_id: "20394207859", gtin: null, msku: null, listing_version: "a".repeat(64), qty: 4 },
      { store_id: "2", store_name: "CN2602", item_id: "21168417269", gtin: null, msku: null, listing_version: "b".repeat(64), qty: 2 },
    ] }),
    candidate("c", { can_approve: false, blocked_reasons: ["WFS_NOT_CONVERTED"] }),
  );
  vi.mocked(decidePacking).mockReset();
  refresh.mockClear();
});
afterEach(cleanup);

test("batch approval approves each selected row in turn and skips blocked rows", async () => {
  vi.mocked(decidePacking).mockImplementation(async (id) => (id === "a" ? order("PK261101-001") : order("PK261101-002", ["PK261101-002", "PK261101-003"])));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<MemoryRouter><QueryClientProvider client={client}>
    <PackingApprovalPanel preferenceScope="test" storeOptions={[]} optionsLoading={false} />
  </QueryClientProvider></MemoryRouter>);

  expect(screen.getByText("拆 2 单")).toBeInTheDocument();
  const boxes = screen.getAllByRole("checkbox").filter((box) => !box.closest("thead"));
  boxes.forEach((box) => fireEvent.click(box));
  const batchButton = await screen.findByRole("button", { name: "批量审批（3）" });
  fireEvent.click(batchButton);

  const dialog = await screen.findByRole("dialog", { name: "批量审批 · 3 张" });
  fireEvent.change(within(dialog).getByLabelText("口令"), { target: { value: "secret" } });
  fireEvent.click(within(dialog).getByRole("button", { name: /提\s*交/ }));

  await waitFor(() => expect(decidePacking).toHaveBeenCalledTimes(2));
  const calls = vi.mocked(decidePacking).mock.calls;
  expect(calls.map(([id, kind]) => [id, kind])).toEqual([["a", "approve"], ["b", "approve"]]);
  expect(calls[1][2]).toMatchObject({ qty: 6, customs: "declare", candidate_version: "v-b", passcode: "secret", rwh: "美中1号仓TX" });
  expect(calls[0][2].idempotency_key).not.toBe(calls[1][2].idempotency_key);

  const result = await screen.findByRole("dialog", { name: "批量审批结果" });
  expect(within(result).getByText(/成功 2 张：PK261101-001、PK261101-002、PK261101-003/)).toBeInTheDocument();
  expect(within(result).getByText(/跳过 1 张：IB-c \/ YC00236（待补资料：该 ItemID 尚未完成 WFS 转换/)).toBeInTheDocument();
  expect(refresh).toHaveBeenCalled();
});
