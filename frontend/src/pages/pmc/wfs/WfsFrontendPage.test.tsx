// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { navigation } from "@/config/navigation";
import WfsFrontendPage from "./WfsFrontendPage";
import WfsQueryPage from "./WfsQueryPage";

const pages = navigation.find((group) => group.key === "pmc")!.children.filter((page) => page.sidebarSection === "pmc-wfs");
vi.mock("./pendingPackingQueries", () => ({ usePendingPacking: () => ({
  list: { data: { data: { items: [], total: 0 } }, isFetching: false },
  summary: { data: { data: { completed: 0, ready: 0, test: 0, waiting: 0, no_box: 0, filled_not_done: 0, available_boxes: 0, available_units: 0 } } },
  options: { data: { data: { stores: [] } }, isFetching: false }, refresh: vi.fn(),
}) }));
// The board and exception pages fetch through react-query; keep this frame test offline with empty results.
const emptyList = { success: true, data: { items: [], total: 0 }, error: null, meta: {}, request_id: "r" };
vi.mock("./shipmentBoardApi", () => ({
  listShipments: vi.fn(() => Promise.resolve({ ...emptyList, data: { ...emptyList.data, data_asof: "2026-10-30T00:00:00Z" } })),
  shipmentSummary: vi.fn(() => Promise.resolve({ ...emptyList, data: { total: 0, pending_lingxing_sync: 0, test: 0 } })),
  boardOptions: vi.fn(() => Promise.resolve({ ...emptyList, data: { stores: [] } })),
  getShipment: vi.fn(() => Promise.reject(new Error("not used"))),
  boardPrefix: "/api/pmc/wfs/shipment-board",
  boardError: () => "",
}));
vi.mock("./exceptionCenterApi", () => ({
  exceptionPrefix: "/api/pmc/wfs/exception-center",
  listCases: vi.fn(() => Promise.resolve(emptyList)),
  exceptionSummary: vi.fn(() => Promise.resolve({ ...emptyList, data: { total: 0, open: 0, in_progress: 0, waiting_external: 0, resolved: 0, closed: 0, due_soon: 0, high: 0 } })),
  exceptionOptions: vi.fn(() => Promise.resolve({ ...emptyList, data: { stores: [], assignees: [] } })),
  getCase: vi.fn(() => Promise.reject(new Error("not used"))),
  assignCase: vi.fn(),
  postCaseEvent: vi.fn(),
  exceptionError: () => "",
}));

const renderWithQuery = (ui: ReactElement) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>,
  );

beforeEach(() => {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(cleanup);

describe("WFS frontend pages", () => {
  it.each(pages)("renders $title", async (page) => {
    const samples: Record<string, { text: string | RegExp; header?: string; search?: string }> = {
      pmc_wfs_pending_packing: { text: "当前条件下暂无已打包完成单据", header: "系统打包单", search: "搜索待发货打包单" },
      pmc_wfs_board: { text: /^当前条件下暂无货件/, header: "货件号", search: "搜索WFS货件看板" },
      pmc_wfs_exceptions: { text: "当前条件下暂无异常货件", header: "货件号", search: "搜索异常中心" },
      pmc_wfs_settings: { text: "上架缓冲天数" },
    };
    const sample = samples[page.key];
    renderWithQuery(<WfsFrontendPage page={page} />);
    expect(screen.getByRole("region", { name: page.title })).toBeInTheDocument();
    expect(await screen.findByText(sample.text)).toBeInTheDocument();
    if (sample.header && sample.search) {
      expect(screen.getByRole("columnheader", { name: sample.header })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: sample.search })).toBeInTheDocument();
    } else {
      expect(screen.getByText(/不请求接口/)).toBeInTheDocument();
    }
  });

  it("uses the packing-approval loading overlay on the shared list frame", () => {
    const page = pages.find((item) => item.key === "pmc_wfs_board")!;
    render(
      <WfsQueryPage
        page={page}
        title="WFS 货件（0 张）"
        tableLabel="WFS 货件表格"
        emptyText="当前条件下暂无货件"
        searchAriaLabel="搜索WFS货件看板"
        inputAriaLabel="搜索WFS货件看板关键字"
        inputPlaceholder="货件号"
        typeAriaLabel="WFS货件看板搜索类型"
        typeOptions={[{ value: "all", label: "货件号" }]}
        columns={[{ title: "货件号", dataIndex: "code" }]}
        scrollX={800}
        keyword=""
        onSearch={() => undefined}
        onReset={() => undefined}
        loading
        loadingLabel="正在加载WFS货件看板，请稍候"
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("正在加载WFS货件看板，请稍候");
  });
});
