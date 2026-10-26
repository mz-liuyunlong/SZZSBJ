// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import ManualPackingModal from "./ManualPackingModal";

vi.mock("./packingApprovalApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./packingApprovalApi")>();
  return {
    ...actual,
    listManualPackingSources: vi.fn().mockResolvedValue({
      success: true,
      data: { items: [], total: 0 },
      error: null,
      meta: {},
      request_id: "test",
    }),
    getManualPackingOptions: vi.fn(),
    submitManualPacking: vi.fn(),
    approvalErrorText: () => "请求失败",
  };
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

test("empty manual packing fields show Chinese required messages", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ManualPackingModal open scope="test" onCancel={vi.fn()} onSubmitted={vi.fn()} />
    </QueryClientProvider>,
  );

  fireEvent.submit(document.querySelector("form")!);

  await waitFor(() => {
    expect(screen.getByText("请填写备货数量")).toBeInTheDocument();
    expect(screen.getByText("请填写添加原因")).toBeInTheDocument();
  });
  expect(screen.queryByText("收货仓")).not.toBeInTheDocument();
  expect(screen.queryByText("姓名")).not.toBeInTheDocument();
  expect(screen.queryByText("口令")).not.toBeInTheDocument();
  expect(screen.queryByText("美中1号仓TX")).not.toBeInTheDocument();
  expect(screen.queryByText("'qty' is required")).not.toBeInTheDocument();
  expect(screen.queryByText("'reason' is required")).not.toBeInTheDocument();
});
