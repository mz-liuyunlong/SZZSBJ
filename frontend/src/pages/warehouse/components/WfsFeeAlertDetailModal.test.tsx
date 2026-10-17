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

describe("WfsFeeAlertDetailModal authorization controls", () => {
  it("does not render write actions for a page-view-only user", () => {
    render(
      <WfsFeeAlertDetailModal
        row={wfsFeeAlertRows[0]}
        currency="USD"
        canFollow={false}
        canArchiveRequest={false}
        onClose={vi.fn()}
        onOpenFollow={vi.fn()}
        onOpenAbandon={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "编辑跟进" })).not.toBeInTheDocument();
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
        onOpenFollow={vi.fn()}
        onOpenAbandon={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "编辑跟进" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "申请放弃跟进" })).toBeInTheDocument();
  });
});
