// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { HashRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import OnboardingGuidePage from "@/pages/help/OnboardingGuidePage";

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

  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  document.documentElement.classList.remove("onboarding-guide-html");
  document.body.classList.remove("onboarding-guide-body");
});

const renderPage = (hash = "#/help/onboarding?returnTo=/products/listing-management") => {
  window.history.replaceState(null, "", hash);

  return render(
    <HashRouter useTransitions={false}>
      <OnboardingGuidePage />
    </HashRouter>,
  );
};

describe("OnboardingGuidePage", () => {
  it("renders a standalone help-center style onboarding guide", () => {
    renderPage();

    expect(screen.getByRole("main", { name: "掌上便捷入职指引" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "掌上便捷入职指引" })).toBeVisible();
    expect(screen.getByRole("complementary", { name: "入职指引目录" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "公司资料" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "系统地图" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "岗位 SOP" })).toBeVisible();
    expect(screen.queryByText("反馈模板")).not.toBeInTheDocument();
    expect(document.body).toHaveClass("onboarding-guide-body");
  });

  it("switches role SOP content and opens sections from the left directory", () => {
    renderPage();

    const sidebar = screen.getByRole("complementary", { name: "入职指引目录" });
    fireEvent.click(
      within(sidebar).getByRole("button", {
        name: /岗位 SOP/,
      }),
    );

    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /财务\s*财务 SOP/ }));

    expect(screen.getByRole("heading", { name: "财务 SOP" })).toBeVisible();
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
    expect(screen.getByText(/查看利润中心、订单利润和单品现金利润/)).toBeVisible();
  });

  it("requires acknowledgement before returning to the original system page", async () => {
    renderPage();

    const completeRegion = screen.getByRole("region", { name: "完成阅读操作" });
    const primaryReturnButton = within(completeRegion).getByRole("button", {
      name: "我已了解，返回系统",
    });

    expect(primaryReturnButton).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "我已阅读并理解基础规则" }));

    await waitFor(() => {
      expect(primaryReturnButton).not.toBeDisabled();
    });

    fireEvent.click(primaryReturnButton);

    expect(window.location.hash).toBe("#/products/listing-management");
  });

  it("shows FAQ and support owner information", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "常见问题" })).toBeVisible();
    expect(screen.getByText("登录不了怎么办？")).toBeVisible();
    expect(screen.getByRole("heading", { name: "负责人支持" })).toBeVisible();
    expect(screen.getByText("系统管理员 / 运营主管")).toBeVisible();
  });
});
