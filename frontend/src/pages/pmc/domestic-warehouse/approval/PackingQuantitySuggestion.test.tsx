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
  getPackingEditOptions: vi.fn().mockResolvedValue({ data: { listings: [{ store_id: "S1",
    store_name: "店铺", item_id: "11111111111", gtin: "00000000000000", msku: "M1",
    listing_version: "a".repeat(64), cross_store: false }], cross_store_proof_available: true } }),
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
  expect(screen.getByText("已按采购计划比例预填，数量可修改")).toBeInTheDocument();
  fireEvent.change(input, { target: { value: "25" } });
  await waitFor(() => expect(screen.getByText("店铺 / 11111111111")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: /^保\s*存$/ }));
  await waitFor(() => expect(submit).toHaveBeenCalledWith(expect.objectContaining({ qty: 25 })));
});

test("independent arrival and split filters are sent to the API", () => {
  const q = approvalQuery({ ...initialPackingApprovalFilters(), arrival: "full", splitArrival: "yes" });
  expect(q.get("arrival")).toBe("full");
  expect(q.get("split_arrival")).toBe("yes");
  expect(approvalBlockedText(["WFS_NOT_CONVERTED"])).toBe("尚未完成 WFS 转换");
});
