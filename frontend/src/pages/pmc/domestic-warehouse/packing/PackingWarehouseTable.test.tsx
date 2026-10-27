// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import PackingWarehouseTable from "./PackingWarehouseTable";
import type { PackingWarehouseRow } from "./packingWarehouseTypes";

function row(overrides: Partial<PackingWarehouseRow> = {}): PackingWarehouseRow {
  return {
    id: "o1",
    source_account_ref: "primary",
    version: 1,
    pk: "PK261026001",
    is_test: true,
    approved_at: "2026-10-26T00:00:00Z",
    approved_date: "2026-10-26",
    inbound_order_sn: "IB261026001",
    inbound_date: "2026-10-26",
    arrival_date: "2026-10-26",
    arrival_status: "inbound_date",
    warehouse_days: 1,
    received_dates: [],
    receipt_order_sns: [],
    purchase_order_sns: [],
    sku: "YC01280",
    product_name: null,
    store_id: "1",
    store_name: "店铺",
    item_id: null,
    gtin: null,
    msku: null,
    approved_quantity: 1,
    stock_balance: 1,
    balance_publication_id: null,
    balance_observed_at: null,
    status: "todo",
    packing_days: 1,
    customs_value: false,
    customs_src: "default",
    product_requirement: { state: "complete", version: "v", source_snapshot_id: null, package: null, reason: null },
    box_set: null,
    current_note: null,
    can_complete: false,
    completion_blocked_reasons: [],
    shipment_status: "not_connected",
    boxspec_sync_status: "not_connected",
    ...overrides,
  };
}

const base = {
  pagination: { page: 1, pageSize: 20 },
  widths: {},
  sort: "approved_desc" as const,
  total: 1,
  loading: false,
  busy: false,
  onAction: vi.fn(),
  onPagination: vi.fn(),
  onResize: vi.fn(),
  onSort: vi.fn(),
};

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

afterEach(cleanup);

test("item column shows one item id link and msku without duplicating the id", () => {
  render(
    <PackingWarehouseTable
      {...base}
      rows={[row({ item_id: "20472717870", msku: "YC00364-1A" })]}
      can={() => true}
      onCustomsChange={vi.fn()}
    />,
  );
  expect(screen.getAllByText("20472717870")).toHaveLength(1);
  expect(screen.getByText("YC00364-1A")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "复制商品ID：20472717870" })).toBeInTheDocument();
});

test("customs column switches in place and the action button is gone", () => {
  const onCustomsChange = vi.fn();
  render(<PackingWarehouseTable {...base} rows={[row({ draft_nos: ["CG261017-039"] })]} can={() => true} onCustomsChange={onCustomsChange} />);

  expect(screen.getByRole("columnheader", { name: /草稿号/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "复制草稿号：CG261017-039" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "改报关" })).not.toBeInTheDocument();
  expect(screen.queryByText("默认")).not.toBeInTheDocument();
  expect(screen.queryByText("人工")).not.toBeInTheDocument();
  fireEvent.mouseDown(screen.getByRole("combobox", { name: /是否报关 PK261026001/ }));
  fireEvent.click(screen.getByText("报关"));
  expect(onCustomsChange).toHaveBeenCalledWith(expect.objectContaining({ id: "o1" }), true);

  fireEvent.mouseDown(screen.getByRole("combobox", { name: /是否报关 PK261026001/ }));
  fireEvent.click(screen.getByText("未知"));
  expect(onCustomsChange).toHaveBeenCalledWith(expect.objectContaining({ id: "o1" }), null);
});

test("customs column stays read-only without the customs permission", () => {
  render(<PackingWarehouseTable {...base} rows={[row()]} can={(kind) => kind !== "customs"} onCustomsChange={vi.fn()} />);

  expect(screen.queryByRole("button", { name: "改报关" })).not.toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: /是否报关 PK261026001/ })).toBeDisabled();
});
