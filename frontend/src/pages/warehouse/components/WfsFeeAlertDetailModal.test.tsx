// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
        onMarkRecovered={vi.fn().mockResolvedValue(undefined)}
        canMarkRecovered={false}
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
        onMarkRecovered={vi.fn().mockResolvedValue(undefined)}
        canMarkRecovered={false}
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
        onMarkRecovered={vi.fn().mockResolvedValue(undefined)}
        canMarkRecovered={false}
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
          salesCoverageStatus: "complete",
          salesCoverageReason: "verified_contiguous_sync_windows",
          salesCoverageStartDate: "2026-07-03",
          salesCoverageEndDate: "2026-10-17",
          feeScopeStatus: "verified_wfs",
          automaticCaseEligible: false,
        }}
        currency="USD"
        canFollow={false}
        canArchiveRequest={false}
        onClose={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onMarkRecovered={vi.fn().mockResolvedValue(undefined)}
        canMarkRecovered={false}
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
    expect(screen.getByText("complete")).toBeInTheDocument();
    expect(screen.getByText("2026-07-03 ～ 2026-10-17")).toBeInTheDocument();
    expect(screen.getByText("verified_wfs")).toBeInTheDocument();
    expect(screen.getByText("仅人工复核")).toBeInTheDocument();
  });
});

describe("WFS recovered amount action", () => {
  it("requires a positive recovered amount before submitting", async () => {
    const onMarkRecovered = vi.fn().mockResolvedValue(undefined);
    render(
      <WfsFeeAlertDetailModal
        row={{ ...wfsFeeAlertRows[0], status: "跟进中" }}
        currency="USD"
        canFollow={false}
        canMarkRecovered
        canArchiveRequest={false}
        onClose={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onMarkRecovered={onMarkRecovered}
        onOpenAbandon={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "标记已追回" }));
    expect(screen.getByText("实际追回金额（USD）")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认已追回" }));

    await waitFor(() => {
      expect(screen.getByText("追回金额必须大于 0")).toBeInTheDocument();
    });
    expect(onMarkRecovered).not.toHaveBeenCalled();
  });

  it("submits the actual recovered amount and optional note", async () => {
    const onMarkRecovered = vi.fn().mockResolvedValue(undefined);
    render(
      <WfsFeeAlertDetailModal
        row={{ ...wfsFeeAlertRows[0], status: "跟进中" }}
        currency="USD"
        canFollow={false}
        canMarkRecovered
        canArchiveRequest={false}
        onClose={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        onMarkRecovered={onMarkRecovered}
        onOpenAbandon={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "标记已追回" }));
    fireEvent.change(screen.getByLabelText("实际追回金额（USD）"), { target: { value: "12.34" } });
    fireEvent.change(screen.getByLabelText("追回说明（选填）"), { target: { value: "沃尔玛已赔付" } });
    fireEvent.click(screen.getByRole("button", { name: "确认已追回" }));

    await waitFor(() => {
      expect(onMarkRecovered).toHaveBeenCalledWith({
        recoveredAmount: 12.34,
        latestFollowNote: "沃尔玛已赔付",
      });
    });
  });

  it("does not show the recovery action without permission or outside following status", () => {
    const common = {
      currency: "USD" as const,
      canFollow: false,
      canArchiveRequest: false,
      onClose: vi.fn(),
      onSubmit: vi.fn().mockResolvedValue(undefined),
      onMarkRecovered: vi.fn().mockResolvedValue(undefined),
      onOpenAbandon: vi.fn(),
    };
    const { rerender } = render(
      <WfsFeeAlertDetailModal
        {...common}
        row={{ ...wfsFeeAlertRows[0], status: "跟进中" }}
        canMarkRecovered={false}
      />,
    );
    expect(screen.queryByRole("button", { name: "标记已追回" })).not.toBeInTheDocument();

    rerender(
      <WfsFeeAlertDetailModal
        {...common}
        row={{ ...wfsFeeAlertRows[0], status: "未开Case" }}
        canMarkRecovered
      />,
    );
    expect(screen.queryByRole("button", { name: "标记已追回" })).not.toBeInTheDocument();
  });
});
