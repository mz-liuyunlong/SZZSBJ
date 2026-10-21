// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PackingApprovalTable from "./PackingApprovalTable";
import type { ApprovalCandidate } from "./packingApprovalApi";

function candidate(overrides: Partial<ApprovalCandidate> = {}): ApprovalCandidate {
  return {
    id: "c1",
    candidate_version: "v",
    source_account_ref: "primary",
    warehouse_id: "16168",
    publication_id: "p",
    board_id: "b",
    inbound_order_sn: "IB261006014",
    sku: "YC00236",
    product_name: null,
    store_id: "1",
    store_name: "HK2614",
    item_id: "20394207859",
    gtin: "00000000000000",
    msku: "YC00236-1A",
    purchase_order_sns: ["PO260001", "PO260002"],
    arrival_purchased: null,
    arrival_received: null,
    arrival_pending: null,
    arrival_status: "unknown",
    candidate_created_on: "2026-10-06",
    overdue: false,
    stock_balance: 10,
    available_quantity: 10,
    default_quantity: 10,
    can_approve: true,
    blocked_reasons: [],
    source_observed_at: "2026-10-06T00:00:00Z",
    ...overrides,
  };
}

afterEach(cleanup);

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

describe("packing approval copy cells", () => {
  it("copies inbound, each purchase order, sku, gtin and item id", () => {
    render(
      <PackingApprovalTable
        pagination={{ page: 1, pageSize: 20 }}
        widths={{}}
        sort="created_desc"
        rows={[candidate()]}
        total={1}
        loading={false}
        canApprove
        canReject
        busy={false}
        onDecision={vi.fn()}
        onPagination={vi.fn()}
        onResize={vi.fn()}
        onSort={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "复制入库单号：IB261006014" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制采购单号：PO260001" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制采购单号：PO260002" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制SKU：YC00236" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制GTIN：00000000000000" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制ItemID：20394207859" })).toBeInTheDocument();
  });

  it("leaves a dash when gtin and item id are missing", () => {
    render(
      <PackingApprovalTable
        pagination={{ page: 1, pageSize: 20 }}
        widths={{}}
        sort="created_desc"
        rows={[candidate({ gtin: null, item_id: null, purchase_order_sns: [] })]}
        total={1}
        loading={false}
        canApprove
        canReject
        busy={false}
        onDecision={vi.fn()}
        onPagination={vi.fn()}
        onResize={vi.fn()}
        onSort={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /复制GTIN/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /复制ItemID/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /复制采购单号/ })).not.toBeInTheDocument();
  });
});
