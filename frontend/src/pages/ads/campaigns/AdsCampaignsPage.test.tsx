// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { navigation } from "@/config/navigation";
import AdsCampaignsPage from "@/pages/ads/campaigns/AdsCampaignsPage";


beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
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

afterEach(() => {
  cleanup();
});

const adsCampaignsPage = navigation
  .find((group) => group.key === "ads")
  ?.children.find((page) => page.key === "ads_campaigns");

describe("AdsCampaignsPage", () => {
  it("renders delivery, reports, and system tabs with the campaign table", () => {
    if (!adsCampaignsPage) throw new Error("ads_campaigns page not found");

    const { container } = render(<AdsCampaignsPage page={adsCampaignsPage} />);

    expect(screen.getByRole("tab", { name: "投放管理" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "数据报表" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "系统能力" })).toBeInTheDocument();

    expect(screen.getByRole("button", { name: /创建广告活动/ })).toBeInTheDocument();
    expect(container).toHaveTextContent("广告活动");
    expect(container).toHaveTextContent("YC00002-手动-ZMS-0803");
  });

  it("switches to reports and system capability tabs", () => {
    if (!adsCampaignsPage) throw new Error("ads_campaigns page not found");

    render(<AdsCampaignsPage page={adsCampaignsPage} />);

    fireEvent.click(screen.getAllByRole("tab", { name: "数据报表" })[0]);
    expect(screen.getByText("今日广告活动数据")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("tab", { name: "系统能力" })[0]);
    expect(screen.getByText("推荐清单")).toBeInTheDocument();
    expect(screen.getByText("快照任务")).toBeInTheDocument();
  });
});
