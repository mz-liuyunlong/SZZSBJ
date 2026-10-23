import { navigation, type NavigationPage } from "@/config/navigation";
import type { MockUserRole } from "@/mocks/auth";

const pagePermissionKey = (groupKey: string, pageKey: string) => {
  const localKey = pageKey.startsWith(`${groupKey}_`)
    ? pageKey.slice(groupKey.length + 1)
    : pageKey;
  return `page:${groupKey.replaceAll("_", "-")}:${localKey.replaceAll("_", "-")}:view`;
};

const PAGE_PERMISSION_BY_KEY = new Map(
  navigation.flatMap((group) =>
    group.children.map((page) => [
      page.key,
      pagePermissionKey(group.key, page.key),
    ] as const),
  ),
);

export function isMockImplementedPage(page: NavigationPage) {
  return page.status !== "hidden" && page.status !== "disabled";
}

export function getPagePermissionKey(page: NavigationPage) {
  return page.viewPermissionKey ?? PAGE_PERMISSION_BY_KEY.get(page.key) ?? page.permissionKey;
}

export function hasPermission(
  permissions: readonly string[] | undefined,
  permissionKey: string,
) {
  return Boolean(
    permissions?.includes("*") || permissions?.includes(permissionKey),
  );
}

export function isMockPageVisibleForRole(
  _role: MockUserRole,
  page: NavigationPage,
  permissions?: readonly string[],
) {
  if (page.status === "disabled" && page.showWhenDisabled) {
    return hasPermission(permissions, getPagePermissionKey(page));
  }
  if (page.status === "hidden" || page.status === "disabled") return false;
  return isMockImplementedPage(page) && hasPermission(permissions, getPagePermissionKey(page));
}

export function isMockPageAccessibleForRole(
  _role: MockUserRole,
  page: NavigationPage,
  permissions?: readonly string[],
) {
  if (page.status === "disabled" || page.status === "hidden") return false;
  return isMockImplementedPage(page) && hasPermission(permissions, getPagePermissionKey(page));
}
