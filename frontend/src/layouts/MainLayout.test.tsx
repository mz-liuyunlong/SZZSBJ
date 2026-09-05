/** Verifies the layout regions and local navigation interactions. */
// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { isValidElement } from "react";
import { HashRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { navigation } from "../config/navigation";
import MainLayout from "./MainLayout";

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

afterEach(cleanup);

const expectSecondaryClosed = () => {
  expect(screen.getByLabelText("二级菜单浮层")).toHaveAttribute(
    "aria-hidden",
    "true",
  );
  expect(screen.getByLabelText("二级菜单浮层")).not.toHaveClass(
    "main-layout__secondary--open",
  );
  expect(screen.getByLabelText("关闭二级菜单")).toBeDisabled();
};

const expectSecondaryOpen = () => {
  expect(screen.getByLabelText("二级菜单浮层")).toHaveAttribute(
    "aria-hidden",
    "false",
  );
  expect(screen.getByLabelText("二级菜单浮层")).toHaveClass(
    "main-layout__secondary--open",
  );
  expect(screen.getByLabelText("关闭二级菜单")).not.toBeDisabled();
};

const requiredGroup = (key: string) => {
  const group = navigation.find((item) => item.key === key);
  if (!group) throw new Error(`Missing navigation group: ${key}`);
  return group;
};

const requiredPage = (groupKey: string, pageKey: string) => {
  const page = requiredGroup(groupKey).children.find(
    (item) => item.key === pageKey,
  );
  if (!page) throw new Error(`Missing navigation page: ${pageKey}`);
  return page;
};

const getTab = (title: string) =>
  within(screen.getByRole("region", { name: "页面标签栏" })).getByRole("tab", {
    name: new RegExp(title),
  });

const getCloseTabButton = (title: string) => {
  const tabContainer = getTab(title).closest(".ant-tabs-tab");
  if (!tabContainer) throw new Error(`Missing tab container: ${title}`);
  return within(tabContainer as HTMLElement).getByRole("tab", {
    name: "关闭标签页",
  });
};

const renderLayout = (path = "/dashboard/today-sales") => {
  window.history.replaceState(null, "", `#${path}`);
  return render(
    <HashRouter useTransitions={false}>
      <MainLayout onLogout={vi.fn()} />
    </HashRouter>,
  );
};

describe("MainLayout", () => {
  it("starts on today sales with the complete topbar and sidebar structure", () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const primarySidebar = screen.getByRole("complementary", {
      name: "一级导航栏",
    });
    const topbar = screen.getByRole("banner", { name: "顶部栏" });
    const content = screen.getByRole("main", { name: "内容区" });
    const currentPage = screen.getByRole("heading", { name: "当前页面" });
    const breadcrumb = screen.getByRole("navigation", { name: "面包屑" });
    const dashboardGroup = requiredGroup("dashboard");
    const todaySales = requiredPage("dashboard", "dashboard_today_sales");
    const primaryMenuItems = within(primaryNavigation).getAllByRole("menuitem");
    expect(primaryMenuItems).toHaveLength(navigation.length);
    navigation.forEach((group, index) => {
      expect(primaryMenuItems[index]).toHaveTextContent(group.title);
      expect(isValidElement(group.icon)).toBe(true);
      expect(typeof group.icon.type).not.toBe("string");
    });

    expectSecondaryClosed();
    expect(document.querySelector(".main-layout")).toBeInTheDocument();
    expect(
      within(primaryNavigation).getByRole("menuitem", {
        name: dashboardGroup.title,
      }),
    ).toHaveClass("ant-menu-item-selected");
    expect(currentPage).toHaveTextContent(todaySales.title);
    expect(within(breadcrumb).getByText(dashboardGroup.title)).toBeVisible();
    expect(within(breadcrumb).getByText(todaySales.title)).toBeVisible();
    expect(getTab(todaySales.title)).toHaveAttribute("aria-selected", "true");
    expect(
      within(topbar).getByRole("button", { name: "回到工作台今日销售" }),
    ).toBeInTheDocument();
    expect(
      within(topbar).queryByRole("button", { name: "折叠侧边栏" }),
    ).not.toBeInTheDocument();
    const sidebarFooter = document.querySelector(".main-layout__sidebar-footer");
    expect(sidebarFooter).toContainElement(
      within(primarySidebar).getByRole("button", { name: "折叠侧边栏" }),
    );
    expect(within(topbar).getByRole("navigation", { name: "面包屑" })).toBeInTheDocument();
    expect(
      within(primarySidebar).queryByRole("button", {
        name: "回到工作台今日销售",
      }),
    ).not.toBeInTheDocument();
    expect(document.querySelector(".main-layout__body")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "页面标签栏" }),
    ).toBeInTheDocument();
    expect(content).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "掌上便捷标识" })).toHaveAttribute(
      "src",
      "/favicon.ico",
    );
    expect(screen.getByText("掌上便捷")).toBeVisible();
  });

  it("keeps tabs, breadcrumb, and content synced to hash history", async () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const content = screen.getByRole("main", { name: "内容区" });
    const currentPage = screen.getByRole("heading", { name: "当前页面" });
    const breadcrumb = screen.getByRole("navigation", { name: "面包屑" });
    const dashboardGroup = requiredGroup("dashboard");
    const todaySales = requiredPage("dashboard", "dashboard_today_sales");
    const adsGroup = requiredGroup("ads");
    const keywordLibrary = requiredPage("ads", "ads_keyword_library");

    const adsGroupItem = within(primaryNavigation).getByRole("menuitem", {
      name: adsGroup.title,
    });
    fireEvent.click(adsGroupItem);
    expect(adsGroupItem).toHaveClass("ant-menu-item-selected");
    expect(currentPage).toHaveTextContent(todaySales.title);
    expect(screen.getByLabelText("二级菜单浮层")).toHaveStyle({
      position: "fixed",
    });
    expectSecondaryOpen();
    expect(primaryNavigation).toBeVisible();
    expect(content).toBeInTheDocument();
    fireEvent.click(
      within(screen.getByLabelText("二级菜单浮层")).getByRole("menuitem", {
        name: keywordLibrary.title,
      }),
    );

    expect(currentPage).toHaveTextContent(keywordLibrary.title);
    expect(within(breadcrumb).getByText(adsGroup.title)).toBeVisible();
    expect(within(breadcrumb).getByText(keywordLibrary.title)).toBeVisible();
    expect(getTab(todaySales.title)).toBeInTheDocument();
    expect(getTab(keywordLibrary.title)).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expectSecondaryClosed();
    expect(window.location.hash).toBe(`#${keywordLibrary.path}`);

    fireEvent.click(getTab(todaySales.title));
    expect(currentPage).toHaveTextContent(todaySales.title);
    expect(getTab(todaySales.title)).toHaveAttribute("aria-selected", "true");
    expect(within(breadcrumb).getByText(dashboardGroup.title)).toBeVisible();
    expect(window.location.hash).toBe(`#${todaySales.path}`);

    fireEvent.click(getTab(keywordLibrary.title));
    expect(currentPage).toHaveTextContent(keywordLibrary.title);
    expect(getTab(keywordLibrary.title)).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(window.location.hash).toBe(`#${keywordLibrary.path}`);

    act(() => window.history.back());
    await waitFor(() => {
      expect(currentPage).toHaveTextContent(todaySales.title);
    });
    expect(window.location.hash).toBe(`#${todaySales.path}`);

    act(() => window.history.forward());
    await waitFor(() => {
      expect(currentPage).toHaveTextContent(keywordLibrary.title);
    });
    expect(window.location.hash).toBe(`#${keywordLibrary.path}`);
  }, 10_000);

  it("closes tabs in memory and restores the default hash from the brand", () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const dashboardGroup = requiredGroup("dashboard");
    const todaySales = requiredPage("dashboard", "dashboard_today_sales");
    const adsGroup = requiredGroup("ads");
    const keywordLibrary = requiredPage("ads", "ads_keyword_library");

    fireEvent.click(
      within(primaryNavigation).getByRole("menuitem", { name: adsGroup.title }),
    );
    fireEvent.click(
      within(screen.getByLabelText("二级菜单浮层")).getByRole("menuitem", {
        name: keywordLibrary.title,
      }),
    );

    fireEvent.click(getCloseTabButton(todaySales.title));
    expect(
      screen.queryByRole("tab", { name: new RegExp(todaySales.title) }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "回到工作台今日销售" }));

    expect(getTab(todaySales.title)).toHaveAttribute("aria-selected", "true");
    expect(
      within(primaryNavigation).getByRole("menuitem", {
        name: dashboardGroup.title,
      }),
    ).toHaveClass("ant-menu-item-selected");
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      todaySales.title,
    );
    expect(window.location.hash).toBe(`#${todaySales.path}`);
    expectSecondaryClosed();

    fireEvent.click(getTab(keywordLibrary.title));
    fireEvent.click(getCloseTabButton(keywordLibrary.title));
    expect(
      screen.queryByRole("tab", { name: new RegExp(keywordLibrary.title) }),
    ).not.toBeInTheDocument();
    expect(getTab(todaySales.title)).toHaveAttribute("aria-selected", "true");

    fireEvent.click(getCloseTabButton(todaySales.title));
    expect(getTab(todaySales.title)).toHaveAttribute("aria-selected", "true");
    expect(window.location.hash).toBe(`#${todaySales.path}`);
  });

  it("switches an open flyout on hover and closes it from the backdrop", () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const productGroup = requiredGroup("products");
    const salesGroup = requiredGroup("sales");
    fireEvent.click(
      within(primaryNavigation).getByRole("menuitem", {
        name: productGroup.title,
      }),
    );
    expectSecondaryOpen();

    fireEvent.mouseEnter(
      within(primaryNavigation).getByRole("menuitem", {
        name: salesGroup.title,
      }),
    );
    expect(
      screen.getByRole("menu", { name: `${salesGroup.title}二级导航` }),
    ).toBeVisible();
    expect(
      within(screen.getByLabelText("二级菜单浮层")).getByText(
        salesGroup.children[0].title,
      ),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "关闭二级菜单" }));

    expectSecondaryClosed();
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      requiredPage("dashboard", "dashboard_today_sales").title,
    );
  });

  it("keeps primary icons and hides labels and secondary navigation when collapsed", () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const dashboardGroup = requiredGroup("dashboard");
    const productGroup = requiredGroup("products");
    const todaySales = requiredPage("dashboard", "dashboard_today_sales");
    const primaryTitle = within(primaryNavigation).getByText(
      dashboardGroup.title,
    );
    const dashboardGroupItem = within(primaryNavigation).getByRole("menuitem", {
      name: dashboardGroup.title,
    });
    fireEvent.click(
      within(primaryNavigation).getByRole("menuitem", {
        name: productGroup.title,
      }),
    );
    expectSecondaryOpen();
    expect(screen.getByRole("button", { name: "关闭二级菜单" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "折叠侧边栏" }));

    expect(
      screen.getByRole("button", { name: "展开侧边栏" }),
    ).toBeInTheDocument();
    expectSecondaryClosed();
    expect(primaryTitle).not.toBeVisible();
    expect(screen.getByRole("img", { name: "掌上便捷标识" })).toBeVisible();
    expect(screen.queryByText("掌上便捷")).not.toBeInTheDocument();
    expect(primaryNavigation.querySelectorAll(".anticon")).toHaveLength(
      navigation.length,
    );

    fireEvent.click(within(primaryNavigation).getAllByRole("menuitem")[1]);
    expectSecondaryOpen();
    expect(screen.getByRole("button", { name: "关闭二级菜单" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "回到工作台今日销售" }));

    expect(dashboardGroupItem).toHaveClass("ant-menu-item-selected");
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      todaySales.title,
    );
    expectSecondaryClosed();
    expect(screen.getByRole("img", { name: "掌上便捷标识" })).toBeVisible();
    expect(screen.queryByText("掌上便捷")).not.toBeInTheDocument();
  });

  it("opens topbar destinations from navigation metadata without exposing hidden pages", async () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const content = screen.getByRole("main", { name: "内容区" });
    const breadcrumb = screen.getByRole("navigation", { name: "面包屑" });
    const tabbar = screen.getByRole("region", { name: "页面标签栏" });
    const productsGroup = requiredGroup("products");
    const settingsGroup = requiredGroup("settings");
    const dataCenterGroup = requiredGroup("data_center");
    const aiAssistant = requiredPage("ai_center", "ai_center_assistant");
    const personalCenter = requiredPage("settings", "settings_personal_center");
    const documentation = requiredPage(
      "data_center",
      "data_center_documentation",
    );

    fireEvent.click(
      within(primaryNavigation).getByRole("menuitem", {
        name: productsGroup.title,
      }),
    );
    expectSecondaryOpen();
    fireEvent.click(screen.getByRole("button", { name: aiAssistant.title }));

    expectSecondaryClosed();
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      aiAssistant.title,
    );
    expect(within(breadcrumb).getByText("AI中心")).toBeVisible();
    expect(within(content).getByText("AI助手内容区")).toBeVisible();
    expect(getTab(aiAssistant.title)).toHaveAttribute("aria-selected", "true");
    expect(window.location.hash).toBe(`#${aiAssistant.path}`);

    fireEvent.click(screen.getByRole("button", { name: aiAssistant.title }));
    expect(
      within(tabbar).getAllByRole("tab", { name: new RegExp(aiAssistant.title) }),
    ).toHaveLength(1);

    fireEvent.click(
      within(primaryNavigation).getByRole("menuitem", {
        name: settingsGroup.title,
      }),
    );
    expect(
      within(screen.getByLabelText("二级菜单浮层")).queryByRole("menuitem", {
        name: personalCenter.title,
      }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "关闭二级菜单" }));

    fireEvent.click(
      within(primaryNavigation).getByRole("menuitem", {
        name: dataCenterGroup.title,
      }),
    );
    expect(
      within(screen.getByLabelText("二级菜单浮层")).queryByRole("menuitem", {
        name: documentation.title,
      }),
    ).not.toBeInTheDocument();

    fireEvent.mouseEnter(screen.getByRole("button", { name: "用户菜单" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: personalCenter.title }));
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      personalCenter.title,
    );
    expect(within(breadcrumb).getByText(settingsGroup.title)).toBeVisible();
    expect(within(content).getByText("个人中心内容区")).toBeVisible();

    fireEvent.mouseEnter(screen.getByRole("button", { name: "用户菜单" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: documentation.title }));
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      documentation.title,
    );
    expect(within(breadcrumb).getByText(dataCenterGroup.title)).toBeVisible();
    expect(within(content).getByText("文档内容区")).toBeVisible();
    expect(window.location.hash).toBe(`#${documentation.path}`);
  });
});
