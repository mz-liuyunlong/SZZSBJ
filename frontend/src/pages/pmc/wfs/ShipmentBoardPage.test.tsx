// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PageHeaderOutletProvider } from "@/components/page/PageShell";
import { navigation } from "@/config/navigation";
import ShipmentBoardPage from "./ShipmentBoardPage";
import * as api from "./shipmentBoardApi";

vi.mock("./shipmentBoardApi");

const page = navigation.find((g) => g.key === "pmc")!.children.find((p) => p.key === "pmc_wfs_board")!;

describe("ShipmentBoardPage", () => {
  beforeEach(() => {
    window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    Object.defineProperty(window, "matchMedia", { configurable: true, value: vi.fn(() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} })) });
  });

  it("loads shipment rows from API", async () => {
    vi.mocked(api.listShipments).mockResolvedValue({
      success: true,
      data: {
        items: [{
          id: "t:WFS-1", shipment_id: "WFS-1", operation_id: "o", ticket_id: "t", ticket_number: 1,
          order_id: "ord", pk: "PK-1", store_id: "s1", business_test: true, its: false,
          label_state: "READY", creation_state: "SUCCEEDED", ticket_state: "SUCCEEDED",
          lingxing_sync_status: "PENDING", declared_units: null, shipped_units: null, received_units: null,
          created_at: "2026-10-29T04:00:00Z",
        }],
        total: 1,
        data_asof: "2026-10-29T04:00:00Z",
      },
      error: null,
      meta: {},
      request_id: "r",
    });
    vi.mocked(api.shipmentSummary).mockResolvedValue({
      success: true,
      data: { total: 1, pending_lingxing_sync: 1, test: 1 },
      error: null,
      meta: {},
      request_id: "r",
    });
    vi.mocked(api.boardOptions).mockResolvedValue({
      success: true,
      data: { stores: [{ value: "s1", label: "店1" }] },
      error: null,
      meta: {},
      request_id: "r",
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <PageHeaderOutletProvider activePageKey={page.key} target={document.body}>
        <QueryClientProvider client={client}>
          <ShipmentBoardPage page={page} scope="test" />
        </QueryClientProvider>
      </PageHeaderOutletProvider>,
    );
    await waitFor(() => expect(screen.getByText("WFS-1")).toBeInTheDocument());
    expect(screen.getByText(/WFS 货件（1 张）/)).toBeInTheDocument();
  });
});
