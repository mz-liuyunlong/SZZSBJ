// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PageHeaderOutletProvider } from "@/components/page/PageShell";
import { navigation } from "@/config/navigation";
import ExceptionCenterPage from "./ExceptionCenterPage";
import * as api from "./exceptionCenterApi";

vi.mock("./exceptionCenterApi");

const page = navigation.find((g) => g.key === "pmc")!.children.find((p) => p.key === "pmc_wfs_exceptions")!;

describe("ExceptionCenterPage", () => {
  beforeEach(() => {
    window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(() => ({
        matches: false,
        addListener() {},
        removeListener() {},
        addEventListener() {},
        removeEventListener() {},
      })),
    });
  });

  it("loads exception cases from API", async () => {
    vi.mocked(api.listCases).mockResolvedValue({
      success: true,
      data: {
        items: [{
          id: "c1",
          shipment_id: "WFS-EX-1",
          rule_family: "arrival_overdue",
          rule_label: "超过预计到仓时间",
          severity: "MEDIUM",
          status: "OPEN",
          status_label: "待处理",
          summary: "测试说明",
          store_id: "s1",
          business_test: true,
          first_detected_at: "2026-10-29T04:00:00Z",
          version: 1,
          rule_version: "M1_STUB",
          lingxing_data_status: "PENDING",
        }],
        total: 1,
      },
      error: null,
      meta: {},
      request_id: "r",
    });
    vi.mocked(api.exceptionSummary).mockResolvedValue({
      success: true,
      data: { open_shipments: 1, open_cases: 1, due_soon_cases: 0 },
      error: null,
      meta: {},
      request_id: "r",
    });
    vi.mocked(api.exceptionOptions).mockResolvedValue({
      success: true,
      data: { stores: [], assignees: [] },
      error: null,
      meta: {},
      request_id: "r",
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <PageHeaderOutletProvider activePageKey={page.key} target={document.body}>
        <QueryClientProvider client={client}>
          <ExceptionCenterPage page={page} scope="test" />
        </QueryClientProvider>
      </PageHeaderOutletProvider>,
    );
    await waitFor(() => expect(screen.getByText("WFS-EX-1")).toBeInTheDocument());
    expect(screen.getByText("超过预计到仓时间")).toBeInTheDocument();
  });
});
