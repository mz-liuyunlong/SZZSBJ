// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ApprovalCandidate } from "./packingApprovalApi";
import PackingApproveConfirmModal from "./PackingApproveConfirmModal";

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
});
afterEach(cleanup);

const row = { pk: "PK261007123", sku: "YC00217", inbound_order_sn: "IB261007008", item_id: "20365620212", gtin: "00730654548398", msku: "YC00217-1U", purchase_order_sns: ["PO260916024"], arrival_purchased: 300, arrival_received: 300, arrival_pending: 0, default_quantity: 300, store_name: "HK2613-李思成(拓美恒)", manual_rwh: "美中1号仓TX", manual_customs: "default", customs_default: false, customs_default_src: "purchase_remark" } as ApprovalCandidate;

test("approve confirm asks for a name and passphrase in Chinese", async () => {
  const onSubmit = vi.fn();
  render(<PackingApproveConfirmModal row={row} busy={false} onCancel={vi.fn()} onSubmit={onSubmit} />);
  expect(screen.getByText("审批通过 · PK261007123 · YC00217")).toBeInTheDocument();
  expect(screen.getByText("吴贤玲")).toBeInTheDocument();
  expect(screen.getByText(/入库单 IB261007008/)).toBeInTheDocument();
  expect(screen.queryByText(/采购单/)).not.toBeInTheDocument();
  expect(screen.queryByText(/备货数量/)).not.toBeInTheDocument();
  expect(screen.queryByText(/填 OWS 号/)).not.toBeInTheDocument();
  fireEvent.submit(document.querySelector("form")!);
  await waitFor(() => expect(screen.getByText("请输入口令")).toBeInTheDocument());
  expect(onSubmit).not.toHaveBeenCalled();
  expect(screen.queryByText("'passcode' is required")).not.toBeInTheDocument();
});
