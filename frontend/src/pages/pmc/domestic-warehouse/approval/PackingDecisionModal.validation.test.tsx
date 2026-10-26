// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ApprovalCandidate } from "./packingApprovalApi";
import PackingDecisionModal from "./PackingDecisionModal";

vi.mock("./packingApprovalApi", async () => {
  const actual = await vi.importActual<typeof import("./packingApprovalApi")>("./packingApprovalApi");
  return { ...actual, getPackingEditOptions: vi.fn().mockResolvedValue({ success: true, data: { listings: [], cross_store_proof_available: false }, error: null, meta: {}, request_id: "test" }) };
});

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

test("empty reject reason shows a Chinese message", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PackingDecisionModal
        row={{ inbound_order_sn: "IB261020012", sku: "YC01280", pk: "PK261015120" } as ApprovalCandidate}
        kind="reject"
        busy={false}
        scope="test"
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    </QueryClientProvider>,
  );

  fireEvent.submit(document.querySelector("form")!);

  expect(screen.getByText("驳回 · PK261015120 · YC01280")).toBeInTheDocument();
  expect(screen.getByText("吴贤玲")).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getByText("请填写驳回原因")).toBeInTheDocument();
  });
  expect(screen.getByText("请输入口令")).toBeInTheDocument();
  expect(screen.queryByText("'note' is required")).not.toBeInTheDocument();
});

test("edit dialog does not ask for warehouse, name, or passcode", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PackingDecisionModal
        row={{ inbound_order_sn: "IB261020003", sku: "YC00364", pk: "PK260915043" } as ApprovalCandidate}
        kind="approve"
        busy={false}
        scope="test"
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    </QueryClientProvider>,
  );

  expect(screen.getByText("修改打包单 PK260915043")).toBeInTheDocument();
  expect(screen.queryByText("收货仓")).not.toBeInTheDocument();
  expect(screen.queryByText("姓名")).not.toBeInTheDocument();
  expect(screen.queryByText("口令")).not.toBeInTheDocument();
  expect(screen.queryByText("美中1号仓TX")).not.toBeInTheDocument();
});
