// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WfsFeeAlertDetailModal from "@/pages/warehouse/components/WfsFeeAlertDetailModal";
import { wfsFeeAlertRows } from "@/pages/warehouse/wfsFeeAlertMockData";

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

describe("WFS automatic follow scheduling and timeline", () => {
  it("shows recent follows first and has no manual follow date", () => {
    const row = {
      ...wfsFeeAlertRows[0],
      status: "跟进中" as const,
      followLog: "First follow\nSecond follow\nThird follow",
      nextFollowAt: "2026-10-27",
    };

    render(
      <WfsFeeAlertDetailModal
        row={row}
        currency="USD"
        canFollow
        canArchiveRequest={false}
        onClose={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onOpenAbandon={vi.fn()}
      />,
    );

    expect(screen.getByText("2026-10-27")).toBeInTheDocument();
    expect(screen.queryByText("下次跟进日期")).not.toBeInTheDocument();

    const container = document.querySelector(".wfs-fee-alert__timeline-scroll");
    expect(container).not.toBeNull();

    const events = Array.from(
      container?.querySelectorAll(".ant-timeline-item-content") ?? [],
    ).map((item) => item.textContent ?? "");

    expect(events[0]).toContain("Third follow");
    expect(events[1]).toContain("Second follow");
    expect(events[2]).toContain("First follow");
    expect(events[events.length - 1]).toContain("发现异常");
  });
});

describe("WfsFeeAlertDetailModal authorization controls", () => {
  it("does not render write actions for a page-view-only user", () => {
    render(
      <WfsFeeAlertDetailModal
        row={wfsFeeAlertRows[0]}
        currency="USD"
        canFollow={false}
        canArchiveRequest={false}
        onClose={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onOpenAbandon={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "保存本次跟进" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "申请放弃跟进" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /关\s*闭/ })).toBeInTheDocument();
  });

  it("renders distinct follow and archive-request actions when granted", () => {
    render(
      <WfsFeeAlertDetailModal
        row={wfsFeeAlertRows[0]}
        currency="USD"
        canFollow
        canArchiveRequest
        onClose={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onOpenAbandon={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "保存本次跟进" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "申请放弃跟进" })).toBeInTheDocument();
  });
});

describe("WfsFeeAlertDetailModal fee evidence", () => {
  it("shows order-count evidence, amount breakdown and freshness separately", () => {
    render(
      <WfsFeeAlertDetailModal
        row={{
          ...wfsFeeAlertRows[0],
          validFeeOrders: 54,
          validSampleUnits: 62,
          modeCount: 32,
          theoreticalOvercharge: 15.2,
          netSampleDifference: 0.99,
          latestSettlementDate: "2026-09-23",
          standardFeeSource: "product_management_rule",
          detectionStatus: "STALE",
          freshnessStatus: "stale",
          detectedAt: "2026-10-20T00:00:00Z",
        }}
        currency="USD"
        canFollow={false}
        canArchiveRequest={false}
        onClose={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onOpenAbandon={vi.fn()}
      />,
    );

    expect(screen.getByText("54")).toBeInTheDocument();
    expect(screen.getByText("62")).toBeInTheDocument();
    expect(screen.getByText("32")).toBeInTheDocument();
    expect(screen.getByText("$15.20")).toBeInTheDocument();
    expect(screen.getByText("$0.99")).toBeInTheDocument();
    expect(screen.getByText("STALE")).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
  });
});
