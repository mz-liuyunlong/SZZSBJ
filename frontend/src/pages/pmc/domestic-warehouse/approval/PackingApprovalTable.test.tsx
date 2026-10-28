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
    draft_nos: ["CG261017-039"],
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
  it("shows cumulative receipts, observed batches and editable advice", () => {
    render(<PackingApprovalTable pagination={{ page: 1, pageSize: 20 }} widths={{}} sort="created_desc"
      rows={[candidate({ arrival_purchased: 100, arrival_received: 60, arrival_pending: 40,
        arrival_status: "partial", split_arrival: true, arrival_batch_count: 2, arrival_batch_index: 2,
        default_quantity: 30, available_quantity: 50, can_approve: false,
        blocked_reasons: ["WFS_NOT_CONVERTED"], quantity_suggestion: { rule: "plan_ratio",
          plan_weights: { "20394207859": 60 }, box_pcs: 10, tail_quantity: 0, notes: [], source_refs: [] } })]}
      total={1} canApprove canReject busy={false} onDecision={vi.fn()} onApprove={vi.fn()}
      onPagination={vi.fn()} onResize={vi.fn()} onSort={vi.fn()} />);
    expect(screen.getByText("100 / 60 / 40")).toBeInTheDocument();
    expect(screen.getByText("部分到货")).toBeInTheDocument();
    expect(screen.getByText("已观测分批")).toBeInTheDocument();
    expect(screen.getByText("第 2 批 / 2 批")).toBeInTheDocument();
    expect(screen.getByText("30 / 50")).toBeInTheDocument();
    expect(screen.getByText("计划比例建议")).toBeInTheDocument();
    expect(screen.getByText("待补资料")).toBeInTheDocument();
  });
  it("copies source fields and links item id to Walmart", () => {
    render(
      <PackingApprovalTable
        pagination={{ page: 1, pageSize: 20 }}
        widths={{}}
        sort="created_desc"
        rows={[candidate()]}
        total={1}
        canApprove
        canReject
        busy={false}
        onDecision={vi.fn()}
        onApprove={vi.fn()}
        onPagination={vi.fn()}
        onResize={vi.fn()}
        onSort={vi.fn()}
      />,
    );
    expect(screen.getByRole("columnheader", { name: /草稿号/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制草稿号：CG261017-039" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制入库单号：IB261006014" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制采购单号：PO260001" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制采购单号：PO260002" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制SKU：YC00236" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制GTIN：00000000000000" })).toBeInTheDocument();
    const itemLink = screen.getByRole("link", { name: "Walmart 商品页：20394207859（新标签页打开）" });
    expect(itemLink).toHaveAttribute("href", "https://www.walmart.com/ip/20394207859");
    expect(itemLink).toHaveAttribute("target", "_blank");
    expect(itemLink).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("button", { name: /修\s*改/ })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "审批通过" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "驳回" })).not.toBeInTheDocument();
  });

  it("leaves a dash when gtin and item id are missing", () => {
    render(
      <PackingApprovalTable
        pagination={{ page: 1, pageSize: 20 }}
        widths={{}}
        sort="created_desc"
        rows={[candidate({ gtin: null, item_id: null, purchase_order_sns: [], draft_nos: [] })]}
        total={1}
        canApprove
        canReject
        busy={false}
        onDecision={vi.fn()}
        onApprove={vi.fn()}
        onPagination={vi.fn()}
        onResize={vi.fn()}
        onSort={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /复制GTIN/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /复制ItemID/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Walmart 商品页/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /复制采购单号/ })).not.toBeInTheDocument();
  });
});
