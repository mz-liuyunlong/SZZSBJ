/**
 * Provides the shared application frame; routing, permissions, and page state live elsewhere.
 */
import { MenuFoldOutlined, MenuUnfoldOutlined } from "@ant-design/icons";
import { Breadcrumb, Button, Layout, Menu, Tabs, Typography } from "antd";
import { useState, type ReactNode } from "react";
import { navigation, type NavigationGroup } from "../config/navigation";
import TopbarActions from "./components/TopbarActions";
import "./MainLayout.css";

const visiblePages = (group: NavigationGroup) =>
  group.children.filter((page) => page.status !== "hidden");

function requireNavigationItem<T>(value: T | undefined, message: string): T {
  if (value === undefined) {
    throw new Error(message);
  }
  return value;
}

const findNavigationPage = (pageKey: string) => {
  for (const group of navigation) {
    const page = group.children.find((item) => item.key === pageKey);
    if (page) return { group, page };
  }
};

const defaultGroup = requireNavigationItem(
  navigation.find((group) => group.key === "dashboard"),
  "MainLayout default navigation group is missing",
);
const defaultPage = requireNavigationItem(
  defaultGroup.children.find((page) => page.key === "dashboard_today_sales"),
  "MainLayout default navigation page is missing",
);
const aiAssistantPage = requireNavigationItem(
  findNavigationPage("ai_center_assistant"),
  "MainLayout AI assistant navigation page is missing",
).page;
const personalCenterPage = requireNavigationItem(
  findNavigationPage("settings_personal_center"),
  "MainLayout personal center navigation page is missing",
).page;
const documentationPage = requireNavigationItem(
  findNavigationPage("data_center_documentation"),
  "MainLayout documentation navigation page is missing",
).page;

interface MainLayoutProps {
  children?: ReactNode;
  onLogout?: () => void;
}

function MainLayout({ children, onLogout = () => undefined }: MainLayoutProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [secondaryOpen, setSecondaryOpen] = useState(false);
  const [activeGroupKey, setActiveGroupKey] = useState(defaultGroup.key);
  const [activePageKey, setActivePageKey] = useState(defaultPage.key);
  const [openTabs, setOpenTabs] = useState([defaultPage.key]);
  const activePageSelection = findNavigationPage(activePageKey) ?? {
    group: defaultGroup,
    page: defaultPage,
  };
  const activePageGroup = activePageSelection.group;
  const activePage = activePageSelection.page;
  const activeGroup =
    navigation.find((group) => group.key === activeGroupKey) ?? activePageGroup;
  const secondaryPages = visiblePages(activeGroup);
  const tabItems = openTabs.flatMap((pageKey) => {
    const selection = findNavigationPage(pageKey);
    return selection
      ? [
          {
            key: pageKey,
            label: selection.page.title,
            icon: selection.group.icon,
            closable: true,
          },
        ]
      : [];
  });

  const selectGroup = (key: string) => {
    const group = navigation.find((item) => item.key === key);
    if (!group) return;

    setActiveGroupKey(key);
    setSecondaryOpen(true);
  };

  const closeSecondaryMenu = () => {
    setSecondaryOpen(false);
  };

  const dismissSecondaryMenu = () => {
    setActiveGroupKey(activePageGroup.key);
    closeSecondaryMenu();
  };

  const openPageByKey = (pageKey: string) => {
    const selection = findNavigationPage(pageKey);
    if (!selection) return;

    setActiveGroupKey(selection.group.key);
    setActivePageKey(selection.page.key);
    setOpenTabs((tabs) =>
      tabs.includes(selection.page.key) ? tabs : [...tabs, selection.page.key],
    );
    closeSecondaryMenu();
  };

  const activateTab = (pageKey: string) => {
    openPageByKey(pageKey);
  };

  const selectPage = (pageKey: string) => {
    const page = activeGroup.children.find((item) => item.key === pageKey);
    if (!page) return;

    openPageByKey(page.key);
  };

  const closeTab = (pageKey: string) => {
    const tabIndex = openTabs.indexOf(pageKey);
    if (tabIndex < 0) return;

    const remainingTabs = openTabs.filter((key) => key !== pageKey);
    if (pageKey !== activePageKey) {
      setOpenTabs(remainingTabs);
      return;
    }

    const adjacentTab =
      remainingTabs[Math.min(tabIndex, remainingTabs.length - 1)];
    if (adjacentTab) {
      setOpenTabs(remainingTabs);
      activateTab(adjacentTab);
      return;
    }

    setOpenTabs([defaultPage.key]);
    setActiveGroupKey(defaultGroup.key);
    setActivePageKey(defaultPage.key);
    closeSecondaryMenu();
  };

  const resetToDefaultPage = () => {
    setActiveGroupKey(defaultGroup.key);
    setActivePageKey(defaultPage.key);
    setOpenTabs((tabs) =>
      tabs.includes(defaultPage.key) ? tabs : [...tabs, defaultPage.key],
    );
    closeSecondaryMenu();
  };

  const toggleSidebar = () => {
    setCollapsed((value) => !value);
    dismissSecondaryMenu();
  };

  return (
    <Layout
      className={`main-layout${collapsed ? " main-layout--collapsed" : ""}`}
    >
      <Layout.Header className="main-layout__header" aria-label="顶部栏">
        <button
          type="button"
          className="main-layout__brand"
          style={{ width: collapsed ? 64 : 168 }}
          aria-label="回到工作台今日销售"
          onClick={resetToDefaultPage}
        >
          <img
            className="main-layout__brand-logo"
            src="/favicon.ico"
            alt="掌上便捷标识"
            width={40}
            height={40}
          />
          {!collapsed && (
            <Typography.Text strong className="main-layout__brand-text">
              掌上便捷
            </Typography.Text>
          )}
        </button>
        <div className="main-layout__header-main">
          <Breadcrumb
            className="main-layout__breadcrumb"
            aria-label="面包屑"
            separator=">"
            items={[
              {
                title: (
                  <span className="main-layout__breadcrumb-group">
                    {activePageGroup.icon}
                    <span>{activePageGroup.title}</span>
                  </span>
                ),
              },
              { title: activePage.title },
            ]}
          />
          <TopbarActions
            aiAssistantPage={aiAssistantPage}
            personalCenterPage={personalCenterPage}
            documentationPage={documentationPage}
            onOpenPage={openPageByKey}
            onRequestOverlayClose={dismissSecondaryMenu}
            onLogout={onLogout}
          />
        </div>
      </Layout.Header>

      <Layout className="main-layout__body" hasSider>
        <Layout.Sider
          className="main-layout__primary"
          width={168}
          collapsedWidth={64}
          collapsed={collapsed}
          collapsible
          trigger={null}
          theme="light"
          aria-label="一级导航栏"
        >
          <Menu
            className="main-layout__primary-menu"
            aria-label="一级导航"
            mode="inline"
            inlineCollapsed={collapsed}
            selectedKeys={[activeGroup.key]}
            onClick={({ key }) => selectGroup(key)}
            items={navigation.map((group) => ({
              key: group.key,
              icon: group.icon,
              label: (
                <span className="main-layout__primary-label">{group.title}</span>
              ),
              title: group.title,
              onMouseEnter: () => {
                if (secondaryOpen && activeGroupKey !== group.key) {
                  selectGroup(group.key);
                }
              },
            }))}
          />
          <div className="main-layout__sidebar-footer">
            <Button
              className="main-layout__collapse-button"
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              aria-label={collapsed ? "展开侧边栏" : "折叠侧边栏"}
              onClick={toggleSidebar}
            >
              {!collapsed && "收起侧栏"}
            </Button>
          </div>
        </Layout.Sider>

        <Layout.Sider
          className={`main-layout__secondary${
            secondaryOpen ? " main-layout__secondary--open" : ""
          }`}
          width={240}
          theme="light"
          aria-label="二级菜单浮层"
          aria-hidden={!secondaryOpen}
          inert={!secondaryOpen}
          style={{ position: "fixed", left: collapsed ? 64 : 168 }}
        >
          <div className="main-layout__secondary-title">
            <Typography.Text strong>{activeGroup.title}</Typography.Text>
          </div>
          <Menu
            className="main-layout__secondary-menu"
            aria-label={`${activeGroup.title}二级导航`}
            mode="inline"
            selectedKeys={activePageKey ? [activePageKey] : []}
            onClick={({ key }) => selectPage(key)}
            items={secondaryPages.map((page) => ({
              key: page.key,
              label: page.title,
              disabled: page.status === "disabled",
            }))}
          />
        </Layout.Sider>

        <button
          type="button"
          className={`main-layout__backdrop${
            secondaryOpen ? " main-layout__backdrop--open" : ""
          }`}
          style={{ left: (collapsed ? 64 : 168) + 240 }}
          aria-label="关闭二级菜单"
          aria-hidden={!secondaryOpen}
          disabled={!secondaryOpen}
          tabIndex={secondaryOpen ? 0 : -1}
          onClick={dismissSecondaryMenu}
        />

        <Layout className="main-layout__workspace">
          <section className="main-layout__tabbar" aria-label="页面标签栏">
            <Tabs
              type="editable-card"
              size="small"
              hideAdd
              activeKey={activePage.key}
              items={tabItems}
              locale={{ removeAriaLabel: "关闭标签页" }}
              onChange={activateTab}
              onEdit={(targetKey, action) => {
                if (action === "remove" && typeof targetKey === "string") {
                  closeTab(targetKey);
                }
              }}
            />
          </section>
          <Layout.Content className="main-layout__content" aria-label="内容区">
            <Typography.Title
              level={4}
              className="main-layout__page-title"
              aria-label="当前页面"
            >
              {activePage.title}
            </Typography.Title>
            {children ?? (
              <Typography.Text type="secondary">
                {activePage.title}内容区
              </Typography.Text>
            )}
          </Layout.Content>
        </Layout>
      </Layout>
    </Layout>
  );
}

export default MainLayout;
