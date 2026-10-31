// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import ListingDetailModal from "./ListingDetailModal";
import { listingManagementMockData } from "../listingManagementData";

vi.mock("antd", () => ({
  Button: ({ children, onClick }: { children: ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>{children}</button>
  ),
  Modal: ({ children, open }: { children: ReactNode; open: boolean }) => open ? <div>{children}</div> : null,
  Tag: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Typography: {
    Title: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
    Text: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  },
}));

afterEach(cleanup);

it("keeps unknown prices, inventory, ads, ratings and monitoring states unknown in detail", () => {
  const row = {
    ...listingManagementMockData[0],
    listPriceKnown: true,
    listPriceCurrency: "",
    salePriceKnown: false,
    wfsAvailableInventoryKnown: false,
    inboundInventoryKnown: false,
    adSpend30DaysKnown: false,
    ratingKnown: false,
    reviewCountKnown: false,
    buyBoxStatus: "待确认",
    resold: "待确认",
  };
  const { container } = render(<ListingDetailModal row={row} onClose={() => undefined} />);

  fireEvent.click(screen.getByRole("button", { name: "销售库存" }));
  const inventory = container.querySelector(".listing-management__detail-main-card");
  expect(inventory).not.toBeNull();
  expect(within(inventory as HTMLElement).getByText("币种未知 19.99")).toBeInTheDocument();
  expect(within(inventory as HTMLElement).getAllByText("未同步")).toHaveLength(5);
  expect(within(inventory as HTMLElement).getByText("无评分")).toBeInTheDocument();
  expect(within(inventory as HTMLElement).queryByText(/\$/)).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "平台状态" }));
  expect(screen.getAllByText("待确认").length).toBeGreaterThan(1);
  fireEvent.click(screen.getByRole("button", { name: "治理记录" }));
  expect(screen.queryByText("暂无跟卖")).not.toBeInTheDocument();
  expect(screen.queryByText("当前正常")).not.toBeInTheDocument();
});

it("shows observed zero inventory instead of a missing-value marker", () => {
  const row = {
    ...listingManagementMockData[0],
    wfsAvailableInventory: 0,
    wfsAvailableInventoryKnown: true,
    inboundInventory: 0,
    inboundInventoryKnown: true,
  };
  const { container } = render(<ListingDetailModal row={row} onClose={() => undefined} />);
  fireEvent.click(screen.getByRole("button", { name: "销售库存" }));
  const grid = container.querySelector(".listing-management__detail-field-grid");
  expect(grid).not.toBeNull();
  const values = Array.from(grid?.querySelectorAll(".listing-management__detail-field-value") ?? [])
    .map((element) => element.textContent);
  expect(values.slice(2, 4)).toEqual(["0", "0"]);
});

it("does not describe stale monitor observations as current normal results", () => {
  const row = {
    ...listingManagementMockData[0],
    monitorAgeHours: 49,
    buyBoxStatus: "拥有",
    resold: "否",
  };
  render(<ListingDetailModal row={row} onClose={() => undefined} />);
  fireEvent.click(screen.getByRole("button", { name: "治理记录" }));

  expect(screen.getByText("监控结果已超过48小时，需重新检查")).toBeInTheDocument();
  expect(screen.getByText("上次监控正常，需重新检查")).toBeInTheDocument();
  expect(screen.getByText("上次未发现跟卖，需重新检查")).toBeInTheDocument();
  expect(screen.queryByText("当前正常")).not.toBeInTheDocument();
  expect(screen.queryByText("暂无跟卖")).not.toBeInTheDocument();
});
