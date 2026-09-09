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
  it("renders navigation metadata and help without exposing permission data", () => {
    const page = DEFAULT_BUSINESS_ROUTE.page;

    render(
      <PageShell page={page} description="页面说明">
        <div>页面内容</div>
      </PageShell>,
    );

    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      page.title,
    );
    expect(screen.getByLabelText(`页面状态：${page.status}`)).toHaveTextContent(
      "规划中",
    );
    expect(screen.getByText("页面说明")).toBeVisible();
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
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      DEFAULT_BUSINESS_ROUTE.page.title,
    );
    expect(screen.getByLabelText("页面状态：planned")).toHaveTextContent(
      "规划中",
    );
    expect(screen.getByText("功能建设中")).toBeVisible();

    rerender(<ComingSoonPage page={hiddenResolution.route.page} />);
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      hiddenResolution.route.page.title,
    );
    expect(screen.getByLabelText("页面状态：hidden")).toHaveTextContent(
      "内部页面",
    );
    expect(screen.getByText("功能建设中")).toBeVisible();
    expect(
      screen.queryByText(hiddenResolution.route.page.permissionKey),
    ).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
});
