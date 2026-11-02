// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { searchPackingListings, type ApprovalCandidate, type ListingHit } from "./packingApprovalApi";
import PackingDecisionModal, { type DecisionValues } from "./PackingDecisionModal";

vi.mock("./packingApprovalApi", async () => {
  const actual = await vi.importActual<typeof import("./packingApprovalApi")>("./packingApprovalApi");
  return { ...actual, searchPackingListings: vi.fn() };
});

const hit = (overrides: Partial<ListingHit> = {}): ListingHit => ({
  store_id: "s1", store_name: "HK2614", item_id: "20987166501", gtin: "00462402942522", msku: "YC01165-1U", local_sku: "YC01165",
  listing_version: "a".repeat(64), cross_store: false, wfs_converted: true, usable: true, blocked_reasons: [], ...overrides,
});
const ok = (items: ListingHit[]) => ({ success: true, data: { items }, error: null, meta: {}, request_id: "test" }) as unknown as Awaited<ReturnType<typeof searchPackingListings>>;
const row = {
  id: "c1", source_account_ref: "primary", warehouse_id: "16168", candidate_version: "v", inbound_order_sn: "IB261023004", sku: "YC01165",
  store_id: null, item_id: null, gtin: null, available_quantity: 50, default_quantity: 50, manual_customs: null, split_lines: [],
} as unknown as ApprovalCandidate;

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
  vi.mocked(searchPackingListings).mockReset();
});
afterEach(cleanup);

function renderModal(onSubmit = vi.fn<(values: DecisionValues) => Promise<void>>().mockResolvedValue(undefined)) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<MemoryRouter><QueryClientProvider client={client}>
    <PackingDecisionModal row={row} kind="approve" busy={false} scope="test" onCancel={vi.fn()} onSubmit={onSubmit} />
  </QueryClientProvider></MemoryRouter>);
  return onSubmit;
}

async function pick(lineIndex: number, typed: string, label: string) {
  const input = screen.getByRole("combobox", { name: `第 ${lineIndex} 行 ItemID` });
  fireEvent.mouseDown(input);
  fireEvent.change(input, { target: { value: typed } });
  const option = await screen.findByText(label, {}, { timeout: 2000 });
  fireEvent.click(option);
}
const saveButton = () => screen.getByRole("button", { name: /保\s*存/ });

test("ItemID search lists Listing hits and fills store / MSKU / GTIN", async () => {
  vi.mocked(searchPackingListings).mockResolvedValue(ok([hit()]));
  renderModal();
  await pick(1, "20987", "HK2614 / 20987166501 / YC01165-1U / YC01165");
  expect(searchPackingListings).toHaveBeenCalledWith(row, "20987", expect.any(AbortSignal));
  expect(screen.getByText("YC01165-1U")).toBeInTheDocument();
  expect(screen.getByText("00462402942522")).toBeInTheDocument();
});

test("an ItemID not converted to WFS cannot be saved", async () => {
  vi.mocked(searchPackingListings).mockResolvedValue(ok([hit({ wfs_converted: false, usable: false, blocked_reasons: ["WFS_NOT_CONVERTED"] })]));
  renderModal();
  await pick(1, "20987", "HK2614 / 20987166501 / YC01165-1U / YC01165");
  fireEvent.change(screen.getByPlaceholderText("例：客户要求分两批 / 换店铺发"), { target: { value: "换店铺发" } });
  expect(await screen.findByText("该 ItemID 尚未完成 WFS 转换，需完成 WFS 转换才能使用")).toBeInTheDocument();
  expect(saveButton()).toBeDisabled();
});

test("an ItemID that belongs to another SKU cannot be saved", async () => {
  vi.mocked(searchPackingListings).mockResolvedValue(ok([hit({ local_sku: "YC01166", usable: false, blocked_reasons: ["SKU_MISMATCH"] })]));
  renderModal();
  await pick(1, "20987", "HK2614 / 20987166501 / YC01165-1U / YC01166");
  fireEvent.change(screen.getByPlaceholderText("例：客户要求分两批 / 换店铺发"), { target: { value: "换店铺发" } });
  expect(await screen.findByText("该 ItemID 在 Listing 管理里属于其他 SKU，不能用于本打包单")).toBeInTheDocument();
  expect(saveButton()).toBeDisabled();
});

test("splitting into two lines within the available stock sends both lines; reason is required", async () => {
  const second = hit({ store_id: "s2", store_name: "CN2602", item_id: "21168417269", msku: "YC01165-1A", listing_version: "b".repeat(64), cross_store: true });
  vi.mocked(searchPackingListings).mockImplementation(async (_row, itemId) => ok(itemId.startsWith("2116") ? [second] : [hit()]));
  const onSubmit = renderModal();
  await pick(1, "20987", "HK2614 / 20987166501 / YC01165-1U / YC01165");
  fireEvent.change(screen.getByRole("spinbutton", { name: "第 1 行数量" }), { target: { value: "30" } });
  fireEvent.click(screen.getByRole("button", { name: "添加一行（拆单）" }));
  await pick(2, "21168", "CN2602 / 21168417269 / YC01165-1A / YC01165");
  fireEvent.change(screen.getByRole("spinbutton", { name: "第 2 行数量" }), { target: { value: "20" } });
  expect(screen.getByText("合计 50 / 可用 50")).toBeInTheDocument();
  expect(saveButton()).toBeDisabled(); // 修改原因 still empty
  fireEvent.change(screen.getByPlaceholderText("例：客户要求分两批 / 换店铺发"), { target: { value: "客户要求分两个店铺发" } });
  await waitFor(() => expect(saveButton()).toBeEnabled());
  fireEvent.click(saveButton());
  await waitFor(() => expect(onSubmit).toHaveBeenCalled());
  const values = onSubmit.mock.calls[0][0];
  expect(values.qty).toBe(50);
  expect(values.edit_reason).toBe("客户要求分两个店铺发");
  expect(values.lines?.map((line) => [line.hit.store_id, line.hit.item_id, line.qty])).toEqual([["s1", "20987166501", 30], ["s2", "21168417269", 20]]);
  expect(within(document.body).getAllByTestId("split-line")).toHaveLength(2);
});

test("a split over the available stock cannot be saved", async () => {
  vi.mocked(searchPackingListings).mockResolvedValue(ok([hit()]));
  renderModal();
  await pick(1, "20987", "HK2614 / 20987166501 / YC01165-1U / YC01165");
  fireEvent.change(screen.getByRole("spinbutton", { name: "第 1 行数量" }), { target: { value: "60" } });
  fireEvent.change(screen.getByPlaceholderText("例：客户要求分两批 / 换店铺发"), { target: { value: "多发一点" } });
  expect(await screen.findByText("拆单数量合计超过可用库存")).toBeInTheDocument();
  expect(saveButton()).toBeDisabled();
});
