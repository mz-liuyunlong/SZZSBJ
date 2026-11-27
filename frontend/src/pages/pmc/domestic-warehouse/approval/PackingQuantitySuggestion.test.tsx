// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { approvalBlockedText, approvalQuery, type ApprovalCandidate } from "./packingApprovalApi";
import { initialPackingApprovalFilters } from "./packingApprovalTypes";
import PackingDecisionModal from "./PackingDecisionModal";

vi.mock("./packingApprovalApi", async () => ({
  ...await vi.importActual("./packingApprovalApi"),
  searchPackingListings: vi.fn().mockResolvedValue({ data: { items: [{ store_id: "S1",
    store_name: "店铺", item_id: "11111111111", gtin: "00000000000000", msku: "M1", local_sku: "SKU",
    listing_version: "a".repeat(64), cross_store: false, wfs_converted: true, usable: true, blocked_reasons: [] }] } }),
}));
beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addListener: vi.fn(),
    removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() });
});
afterEach(cleanup);

test("prefills ratio advice and submits a manually changed quantity", async () => {
  const submit = vi.fn().mockResolvedValue(undefined);
  const row = { id: "c1", source_account_ref: "primary", inbound_order_sn: "IB1", sku: "SKU",
    store_id: "S1", item_id: "11111111111", available_quantity: 100, default_quantity: 60,
    quantity_suggestion: { rule: "plan_ratio", plan_weights: { "11111111111": 60 }, box_pcs: 10,
      tail_quantity: 3, notes: ["不足整箱尾差 3 件，请人工确认"], source_refs: [] },
  } as unknown as ApprovalCandidate;
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <PackingDecisionModal row={row} kind="approve" busy={false} scope="test"
      onCancel={vi.fn()} onSubmit={submit} />
  </QueryClientProvider>);
  const input = await screen.findByRole("spinbutton");
  await waitFor(() => expect(input).toHaveValue("60"));
  expect(screen.queryByText("已按采购计划比例预填，数量可修改")).not.toBeInTheDocument();
  expect(screen.queryByText(/请人工确认备货数量/)).not.toBeInTheDocument();
  fireEvent.change(input, { target: { value: "25" } });
  // The row's current identity is looked up by ItemID and pre-selected.
  await waitFor(() => expect(screen.getByText("店铺 / 11111111111 / M1 / SKU")).toBeInTheDocument());
  fireEvent.change(screen.getByPlaceholderText("例：客户要求分两批 / 换店铺发"), { target: { value: "按实际到货调整" } });
  const save = screen.getByRole("button", { name: /^保\s*存$/ });
  await waitFor(() => expect(save).toBeEnabled());
  fireEvent.click(save);
  await waitFor(() => expect(submit).toHaveBeenCalledWith(expect.objectContaining({ qty: 25, edit_reason: "按实际到货调整" })));
});

test("independent arrival and split filters are sent to the API", () => {
  const q = approvalQuery({ ...initialPackingApprovalFilters(), arrival: "full", splitArrival: "yes" });
  expect(q.get("arrival")).toBe("full");
  expect(q.get("split_arrival")).toBe("yes");
  expect(approvalBlockedText(["WFS_NOT_CONVERTED"])).toBe("该 ItemID 尚未完成 WFS 转换，需完成 WFS 转换才能使用");
});
