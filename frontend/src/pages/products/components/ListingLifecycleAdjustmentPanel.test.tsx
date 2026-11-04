// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ListingLifecycleAdjustmentPanel from "./ListingLifecycleAdjustmentPanel";

const backendRequest = vi.hoisted(() => vi.fn());
vi.mock("@/api/backendApi", () => ({ backendRequest }));

beforeEach(() => {
  backendRequest.mockReset();
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })),
  });
});
afterEach(cleanup);

const permissions = [
  "action:products:listing-management:request-lifecycle",
  "action:products:listing-management:approve-lifecycle",
];

it("keeps manual lifecycle writes hidden while publication is disabled", async () => {
  backendRequest.mockImplementation((path: string) => Promise.resolve(path.includes("rule-config")
    ? { data: { publish_enabled: false } }
    : { data: { items: [], total: 0 } }));
  render(<ListingLifecycleAdjustmentPanel listingId="synthetic-id" permissions={permissions} onApplied={() => undefined} />);
  await vi.waitFor(() => expect(backendRequest).toHaveBeenCalledTimes(2));
  expect(screen.queryByText("人工生命周期调整")).not.toBeInTheDocument();
});

it("requires a separate confirmed approval and reloads the audited history", async () => {
  backendRequest.mockImplementation((path: string) => Promise.resolve(path.includes("rule-config")
    ? { data: { publish_enabled: true } }
    : { data: { items: [{
      id: "synthetic-adjustment", expected_stage: "测品期", requested_stage: "启动期",
      reason: "synthetic evidence", status: "pending", requested_by: "synthetic-requester",
      requested_at: "2026-01-15T00:00:00Z", decided_by: null, decision_note: null,
    }], total: 1 } }));
  const onApplied = vi.fn();
  render(<ListingLifecycleAdjustmentPanel listingId="synthetic-id" permissions={permissions} onApplied={onApplied} />);
  fireEvent.click(await screen.findByRole("button", { name: "审批通过" }));
  const confirm = screen.getByRole("button", { name: "OK" });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByPlaceholderText("填写审批说明（至少5个字符）"), { target: { value: "synthetic approval note" } });
  fireEvent.change(screen.getAllByPlaceholderText("输入 CONFIRM_LISTING_LIFECYCLE 进行二次确认").at(-1)!, {
    target: { value: "CONFIRM_LISTING_LIFECYCLE" },
  });
  fireEvent.click(confirm);
  await vi.waitFor(() => expect(backendRequest).toHaveBeenCalledWith(
    "/api/listings/lifecycle-adjustments/synthetic-adjustment/decision",
    expect.objectContaining({ method: "POST" }),
  ));
  await vi.waitFor(() => expect(onApplied).toHaveBeenCalledOnce());
});
