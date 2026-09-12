/** Verifies shared page metadata presentation without duplicating layout navigation. */
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ComingSoonPage from "@/pages/ComingSoonPage";
import {
  DEFAULT_BUSINESS_ROUTE,
  resolveRoute,
} from "@/router/routeResolver";
import PageShell from "@/components/page/PageShell";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PageShell", () => {
  it("labels the page region and keeps help without rendering title or status chrome", () => {
    const page = DEFAULT_BUSINESS_ROUTE.page;

    render(
      <PageShell page={page} description="页面说明">
        <div>页面内容</div>
      </PageShell>,
    );

    expect(screen.getByRole("region", { name: page.title })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "当前页面" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(`页面状态：${page.status}`)).not.toBeInTheDocument();
    expect(screen.queryByText("页面说明")).not.toBeInTheDocument();
    expect(screen.getByText("页面内容")).toBeVisible();

    const help = screen.getByRole("link", {
      name: `在新标签页打开${page.help.title}`,
    });
    expect(help).toHaveAttribute("href", page.help.helpUrl);
    expect(help).toHaveAttribute("target", "_blank");
    expect(help).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.queryByText(page.permissionKey)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "面包屑" }),
    ).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uses the same no-API placeholder for visible and hidden pages", () => {
    const hiddenResolution = resolveRoute("/data-center/documentation");
    if (hiddenResolution.kind !== "allowed") {
      throw new Error("Expected documentation to remain an allowed hidden page");
    }

    const { rerender } = render(
      <ComingSoonPage page={DEFAULT_BUSINESS_ROUTE.page} />,
    );
    expect(screen.getByRole("region", {
      name: DEFAULT_BUSINESS_ROUTE.page.title,
    })).toBeVisible();
    expect(screen.queryByLabelText("页面状态：planned")).not.toBeInTheDocument();
    expect(screen.getByText("功能建设中")).toBeVisible();

    rerender(<ComingSoonPage page={hiddenResolution.route.page} />);
    expect(screen.getByRole("region", {
      name: hiddenResolution.route.page.title,
    })).toBeVisible();
    expect(screen.queryByLabelText("页面状态：hidden")).not.toBeInTheDocument();
    expect(screen.getByText("功能建设中")).toBeVisible();
    expect(
      screen.queryByText(hiddenResolution.route.page.permissionKey),
    ).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
});
