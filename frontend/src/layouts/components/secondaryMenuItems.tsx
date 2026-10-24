/** Navigation-only sections remain non-routable; leaf permissions are filtered by MainLayout. */
import type { MenuProps } from "antd";
import type { NavigationGroup, NavigationPage } from "@/config/navigation";
import { isRoutableStatus } from "@/router/routeResolver";

export function secondaryMenuItems(group: NavigationGroup, pages: NavigationPage[]): MenuProps["items"] {
  const leaf = (page: NavigationPage) => ({
    key: page.key,
    className: page.sidebarSection ? "main-layout__section-leaf" : undefined,
    label: page.description || page.showWhenDisabled ? <span className="main-layout__menu-label"><span>{page.title}</span>{page.description && <small>{page.description}</small>}{page.status === "disabled" && <small>待开发</small>}</span> : page.title,
    disabled: !isRoutableStatus(page.status),
  });
  const root = pages.filter((p) => !p.sidebarSection).map(leaf);
  const sections = (group.sidebarSections ?? []).flatMap((section) => {
    const children = pages.filter((p) => p.sidebarSection === section.key).map(leaf);
    return children.length ? [{ type: "group" as const, key: section.key, className: "main-layout__menu-section", label: section.title, children }] : [];
  });
  return [...root, ...sections];
}
