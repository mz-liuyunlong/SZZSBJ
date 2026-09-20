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
import { isValidElement, useState, type ReactNode } from "react";
import { HashRouter } from "react-router-dom";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { navigation, type NavigationPage } from "@/config/navigation";
import { DEFAULT_BUSINESS_PATH, resolveRoute } from "@/router/routeResolver";
import PageShell from "@/components/page/PageShell";
import MainLayout from "@/layouts/MainLayout";
import {
  MAX_OPEN_TABS,
  TAB_WORKSPACE_STORAGE_KEY,
  TAB_WORKSPACE_VERSION,
} from "@/layouts/useTabWorkspace";

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

beforeEach(() => {
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

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

const renderLayout = (
  path = DEFAULT_BUSINESS_PATH,
  renderPage?: (page: NavigationPage) => ReactNode,
) => {
  window.history.replaceState(null, "", `#${path}`);
  return render(
    <HashRouter useTransitions={false}>
      <MainLayout onLogout={vi.fn()} renderPage={renderPage} />
    </HashRouter>,
  );
};

function StatefulPageFixture({ page }: { page: NavigationPage }) {
  const [value, setValue] = useState("");
  return (
    <label>
      {page.title}测试状态
      <input
        aria-label={`${page.title}测试状态`}
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
    </label>
  );
}

describe("MainLayout", () => {
  it("starts on listing management with the complete topbar and sidebar structure", () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const primarySidebar = screen.getByRole("complementary", {
      name: "一级导航栏",
    });
    const topbar = screen.getByRole("banner", { name: "顶部栏" });
    const content = screen.getByRole("main", { name: "内容区" });
    const currentPage = screen.getByRole("heading", { name: "当前页面" });
    const breadcrumb = screen.getByRole("navigation", { name: "面包屑" });
    const productsGroup = requiredGroup("products");
    const listingManagement = requiredPage("products", "products_listing_management");
    void listingManagement;
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
        name: productsGroup.title,
      }),
    ).toHaveClass("ant-menu-item-selected");
    expect(currentPage).toHaveTextContent(listingManagement.title);
    expect(within(breadcrumb).getByText(productsGroup.title)).toBeVisible();
    expect(within(breadcrumb).getByText(listingManagement.title)).toBeVisible();
    expect(getTab(listingManagement.title)).toHaveAttribute("aria-selected", "true");
    expect(
      within(topbar).getByRole("button", { name: "回到Listing管理首页" }),
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
        name: "回到Listing管理首页",
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

  it("hosts global sync, help, and active page actions beside the breadcrumb", async () => {
    const productPage = requiredPage("products", "products_product_management");
    renderLayout(productPage.path, (page) => (
      <PageShell
        page={page}
        headerActions={<span>页面操作</span>}
      >
        <div>页面主体</div>
      </PageShell>
    ));

    const topbar = screen.getByRole("banner", { name: "顶部栏" });
    const pageActions = within(topbar).getByRole("group", { name: "页面级操作" });
    await waitFor(() => {
      expect(within(pageActions).getByText("页面操作")).toBeVisible();
    });
    expect(within(topbar).getByText("同步时间：待接入")).toBeVisible();
    expect(within(topbar).getByRole("button", { name: "帮助" })).toBeVisible();
    expect(within(topbar).queryByRole("button", { name: /刷新|同步/ })).not.toBeInTheDocument();
    expect(screen.getAllByText("帮助")).toHaveLength(1);
    const content = screen.getByRole("main", { name: "内容区" });
    expect(within(content).queryByText("页面操作")).not.toBeInTheDocument();
    expect(within(content).queryByText("帮助")).not.toBeInTheDocument();
  });

  it("keeps tabs, breadcrumb, and content synced to hash history", async () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const content = screen.getByRole("main", { name: "内容区" });
    const currentPage = screen.getByRole("heading", { name: "当前页面" });
    const breadcrumb = screen.getByRole("navigation", { name: "面包屑" });
    const productsGroup = requiredGroup("products");
    const listingManagement = requiredPage("products", "products_listing_management");
    void listingManagement;
    const adsGroup = requiredGroup("ads");
    const keywordLibrary = requiredPage("ads", "ads_keyword_library");

    const adsGroupItem = within(primaryNavigation).getByRole("menuitem", {
      name: adsGroup.title,
    });
    fireEvent.click(adsGroupItem);
    expect(adsGroupItem).toHaveClass("ant-menu-item-selected");
    expect(currentPage).toHaveTextContent(listingManagement.title);
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
    expect(getTab(listingManagement.title)).toBeInTheDocument();
    expect(getTab(keywordLibrary.title)).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expectSecondaryClosed();
    expect(window.location.hash).toBe(`#${keywordLibrary.path}`);

    fireEvent.click(adsGroupItem);
    fireEvent.click(
      within(screen.getByLabelText("二级菜单浮层")).getByRole("menuitem", {
        name: keywordLibrary.title,
      }),
    );
    expect(
      within(screen.getByRole("region", { name: "页面标签栏" })).getAllByRole(
        "tab",
        { name: new RegExp(keywordLibrary.title) },
      ),
    ).toHaveLength(1);

    fireEvent.click(getTab(listingManagement.title));
    expect(currentPage).toHaveTextContent(listingManagement.title);
    expect(getTab(listingManagement.title)).toHaveAttribute("aria-selected", "true");
    expect(within(breadcrumb).getByText(productsGroup.title)).toBeVisible();
    expect(window.location.hash).toBe(`#${DEFAULT_BUSINESS_PATH}`);

    fireEvent.click(getTab(keywordLibrary.title));
    expect(currentPage).toHaveTextContent(keywordLibrary.title);
    expect(getTab(keywordLibrary.title)).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(window.location.hash).toBe(`#${keywordLibrary.path}`);

    act(() => window.history.back());
    await waitFor(() => {
      expect(currentPage).toHaveTextContent(listingManagement.title);
    });
    expect(window.location.hash).toBe(`#${DEFAULT_BUSINESS_PATH}`);

    act(() => window.history.forward());
    await waitFor(() => {
      expect(currentPage).toHaveTextContent(keywordLibrary.title);
    });
    expect(window.location.hash).toBe(`#${keywordLibrary.path}`);
  }, 10_000);

  it("keeps Home fixed and closes an inactive tab predictably", () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const productsGroup = requiredGroup("products");
    const listingManagement = requiredPage("products", "products_listing_management");
    void listingManagement;
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

    const homeTabContainer = getTab(listingManagement.title).closest(".ant-tabs-tab");
    if (!homeTabContainer) throw new Error("Missing Home tab container");
    expect(
      within(homeTabContainer as HTMLElement).queryByRole("tab", {
        name: "关闭标签页",
      }),
    ).not.toBeInTheDocument();

    fireEvent.click(getTab(listingManagement.title));
    fireEvent.click(getCloseTabButton(keywordLibrary.title));
    expect(
      screen.queryByRole("tab", { name: new RegExp(keywordLibrary.title) }),
    ).not.toBeInTheDocument();

    expect(getTab(listingManagement.title)).toHaveAttribute("aria-selected", "true");
    expect(
      within(primaryNavigation).getByRole("menuitem", {
        name: productsGroup.title,
      }),
    ).toHaveClass("ant-menu-item-selected");
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      listingManagement.title,
    );
    expect(window.location.hash).toBe(`#${DEFAULT_BUSINESS_PATH}`);
    expectSecondaryClosed();

  });

  it("returns to Home after closing the active tab", () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const listingManagement = requiredPage("products", "products_listing_management");
    void listingManagement;
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
    fireEvent.click(getCloseTabButton(keywordLibrary.title));

    expect(
      screen.queryByRole("tab", { name: new RegExp(keywordLibrary.title) }),
    ).not.toBeInTheDocument();
    expect(getTab(listingManagement.title)).toHaveAttribute("aria-selected", "true");
    expect(window.location.hash).toBe(`#${DEFAULT_BUSINESS_PATH}`);
  });

  it("reopens a closed active tab when browser Back restores its URL", async () => {
    const adsGroup = requiredGroup("ads");
    const listingManagement = requiredPage("products", "products_listing_management");
    void listingManagement;
    const keywordLibrary = requiredPage("ads", "ads_keyword_library");
    renderLayout(DEFAULT_BUSINESS_PATH, (page) => (
      <StatefulPageFixture page={page} />
    ));

    fireEvent.click(
      within(screen.getByRole("menu", { name: "一级导航" })).getByRole(
        "menuitem",
        { name: adsGroup.title },
      ),
    );
    fireEvent.click(
      within(screen.getByLabelText("二级菜单浮层")).getByRole("menuitem", {
        name: keywordLibrary.title,
      }),
    );
    fireEvent.click(getCloseTabButton(keywordLibrary.title));
    expect(window.location.hash).toBe(`#${DEFAULT_BUSINESS_PATH}`);
    expect(
      screen.queryByRole("tab", { name: new RegExp(keywordLibrary.title) }),
    ).not.toBeInTheDocument();

    act(() => window.history.back());

    await waitFor(() => {
      expect(window.location.hash).toBe(`#${keywordLibrary.path}`);
      expect(getTab(keywordLibrary.title)).toHaveAttribute(
        "aria-selected",
        "true",
      );
    });
    expect(
      within(screen.getByRole("navigation", { name: "面包屑" })).getByText(
        keywordLibrary.title,
      ),
    ).toBeVisible();
    expect(
      screen.getByLabelText(`${keywordLibrary.title}测试状态`),
    ).toBeVisible();
    await waitFor(() => {
      const stored = JSON.parse(
        sessionStorage.getItem(TAB_WORKSPACE_STORAGE_KEY) ?? "null",
      );
      expect(stored).toEqual({
        version: TAB_WORKSPACE_VERSION,
        openPaths: [DEFAULT_BUSINESS_PATH, keywordLibrary.path],
        activePath: keywordLibrary.path,
      });
      expect(Object.keys(stored)).toEqual([
        "version",
        "openPaths",
        "activePath",
      ]);
    });
  });

  it("keeps open tab pages mounted on tab switches and remounts them on refresh", async () => {
    const adsGroup = requiredGroup("ads");
    const listingManagement = requiredPage("products", "products_listing_management");
    void listingManagement;
    const keywordLibrary = requiredPage("ads", "ads_keyword_library");
    const renderPage = (page: NavigationPage) => (
      <StatefulPageFixture page={page} />
    );
    const view = renderLayout(DEFAULT_BUSINESS_PATH, renderPage);
    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });

    fireEvent.change(screen.getByLabelText(`${listingManagement.title}测试状态`), {
      target: { value: "首页草稿" },
    });
    fireEvent.click(
      within(primaryNavigation).getByRole("menuitem", { name: adsGroup.title }),
    );
    fireEvent.click(
      within(screen.getByLabelText("二级菜单浮层")).getByRole("menuitem", {
        name: keywordLibrary.title,
      }),
    );
    fireEvent.change(screen.getByLabelText(`${keywordLibrary.title}测试状态`), {
      target: { value: "词库草稿" },
    });

    fireEvent.click(getTab(listingManagement.title));
    expect(screen.getByLabelText(`${listingManagement.title}测试状态`)).toHaveValue("首页草稿");

    fireEvent.click(getTab(keywordLibrary.title));
    expect(screen.getByLabelText(`${keywordLibrary.title}测试状态`)).toHaveValue("词库草稿");

    fireEvent.change(screen.getByLabelText(`${keywordLibrary.title}测试状态`), {
      target: { value: "刷新前草稿" },
    });
    await waitFor(() => {
      expect(
        JSON.parse(sessionStorage.getItem(TAB_WORKSPACE_STORAGE_KEY) ?? "null"),
      ).toEqual({
        version: TAB_WORKSPACE_VERSION,
        openPaths: [DEFAULT_BUSINESS_PATH, keywordLibrary.path],
        activePath: keywordLibrary.path,
      });
    });

    view.unmount();
    renderLayout(keywordLibrary.path, renderPage);
    expect(getTab(listingManagement.title)).toBeInTheDocument();
    expect(getTab(keywordLibrary.title)).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByLabelText(`${keywordLibrary.title}测试状态`)).toHaveValue(
      "",
    );
    expect(sessionStorage.getItem(TAB_WORKSPACE_STORAGE_KEY)).not.toContain(
      "刷新前草稿",
    );
  });

  it("refuses a thirteenth tab without evicting the existing workspace", async () => {
    const allowedSelections = navigation.flatMap((group) =>
      group.children
        .filter(
          (page) =>
            page.status !== "hidden" && resolveRoute(page.path).kind === "allowed",
        )
        .map((page) => ({ group, page })),
    );
    const initialSelections = allowedSelections.slice(0, MAX_OPEN_TABS);
    const target = allowedSelections[MAX_OPEN_TABS];
    if (!target) throw new Error("Missing thirteenth navigation fixture");
    const initialPaths = initialSelections.map(({ page }) => page.path);
    const restoredPaths = [
      DEFAULT_BUSINESS_PATH,
      ...initialPaths.filter((path) => path !== DEFAULT_BUSINESS_PATH),
    ].slice(0, MAX_OPEN_TABS);
    sessionStorage.setItem(
      TAB_WORKSPACE_STORAGE_KEY,
      JSON.stringify({
        version: TAB_WORKSPACE_VERSION,
        openPaths: initialPaths,
        activePath: DEFAULT_BUSINESS_PATH,
      }),
    );
    renderLayout();

    fireEvent.click(
      within(screen.getByRole("menu", { name: "一级导航" })).getByRole(
        "menuitem",
        { name: target.group.title },
      ),
    );
    fireEvent.click(
      within(screen.getByLabelText("二级菜单浮层")).getByRole("menuitem", {
        name: target.page.title,
      }),
    );

    expect(
      await screen.findByText("最多打开 12 个标签页，请先关闭一个标签页。"),
    ).toBeVisible();
    expect(
      document.querySelectorAll(".main-layout__tabbar .ant-tabs-tab"),
    ).toHaveLength(MAX_OPEN_TABS);
    expect(screen.queryByRole("tab", { name: new RegExp(target.page.title) })).not.toBeInTheDocument();
    expect(window.location.hash).toBe(`#${DEFAULT_BUSINESS_PATH}`);
    expect(
      JSON.parse(sessionStorage.getItem(TAB_WORKSPACE_STORAGE_KEY) ?? "null")
        .openPaths,
    ).toEqual(restoredPaths);

    act(() => {
      window.history.pushState(null, "", `#${target.page.path}`);
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    await waitFor(() => {
      expect(window.location.hash).toBe(`#${DEFAULT_BUSINESS_PATH}`);
    });
    expect(getTab(requiredPage("products", "products_listing_management").title)).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("main", { name: "内容区" })).not.toBeEmptyDOMElement();
  });

  it("switches an open flyout on hover and closes it from the backdrop", async () => {
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
      await screen.findByRole("menu", { name: `${salesGroup.title}二级导航` }),
    ).toBeVisible();
    expect(
      within(screen.getByLabelText("二级菜单浮层")).getByText(
        salesGroup.children[0].title,
      ),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "关闭二级菜单" }));

    expectSecondaryClosed();
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      requiredPage("products", "products_listing_management").title,
    );
  });

  it("keeps primary icons and hides labels and secondary navigation when collapsed", () => {
    renderLayout();

    const primaryNavigation = screen.getByRole("menu", { name: "一级导航" });
    const productsGroup = requiredGroup("products");
    const productGroup = requiredGroup("products");
    const listingManagement = requiredPage("products", "products_listing_management");
    void listingManagement;
    const primaryTitle = within(primaryNavigation).getByText(
      productsGroup.title,
    );
    const salesGroupItem = within(primaryNavigation).getByRole("menuitem", {
      name: productsGroup.title,
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

    fireEvent.click(screen.getByRole("button", { name: "回到Listing管理首页" }));

    expect(salesGroupItem).toHaveClass("ant-menu-item-selected");
    expect(screen.getByRole("heading", { name: "当前页面" })).toHaveTextContent(
      listingManagement.title,
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
