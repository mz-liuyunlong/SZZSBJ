import {
  navigation,
  type NavigationGroup,
  type NavigationPage,
  type PageStatus,
} from "../config/navigation";

export interface NavigationRoute {
  group: NavigationGroup;
  page: NavigationPage;
}

export type RouteResolution =
  | { kind: "allowed"; route: NavigationRoute }
  | { kind: "disabled"; route: NavigationRoute }
  | { kind: "unknown" };

const navigationRoutes = navigation.flatMap((group) =>
  group.children.map((page) => ({ group, page })),
);

export const isRoutableStatus = (status: PageStatus) => status !== "disabled";

export const findRouteByKey = (pageKey: string) =>
  navigationRoutes.find(({ page }) => page.key === pageKey);

export const resolveRoute = (path: string): RouteResolution => {
  const route = navigationRoutes.find(({ page }) => page.path === path);
  if (!route) return { kind: "unknown" };
  return isRoutableStatus(route.page.status)
    ? { kind: "allowed", route }
    : { kind: "disabled", route };
};

export const getSidebarPages = (group: NavigationGroup) =>
  group.children.filter((page) => page.status !== "hidden");

const defaultRoute = findRouteByKey("dashboard_today_sales");
if (!defaultRoute || !isRoutableStatus(defaultRoute.page.status)) {
  throw new Error("Default business route is missing or disabled");
}

export const DEFAULT_BUSINESS_ROUTE = defaultRoute;
export const DEFAULT_BUSINESS_PATH = defaultRoute.page.path;
