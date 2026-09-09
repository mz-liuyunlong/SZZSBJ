import { describe, expect, it } from "vitest";
import { navigation } from "@/config/navigation";
import {
  MAX_OPEN_TABS,
  restoreTabWorkspace,
  TAB_WORKSPACE_VERSION,
} from "@/layouts/useTabWorkspace";
import {
  DEFAULT_BUSINESS_PATH,
  DEFAULT_BUSINESS_ROUTE,
  findRouteByKey,
  getSidebarPages,
  isRoutableStatus,
  resolveRoute,
} from "@/router/routeResolver";

describe("routeResolver", () => {
  it("derives route metadata from navigation", () => {
    navigation.forEach((group) => {
      group.children.forEach((page) => {
        const resolution = resolveRoute(page.path);
        expect(resolution.kind).toBe(isRoutableStatus(page.status) ? "allowed" : "disabled");
        if (resolution.kind !== "unknown") {
          expect(resolution.route.group).toBe(group);
          expect(resolution.route.page).toBe(page);
        }
      });
    });
  });

  it("uses today sales from navigation as the default business route", () => {
    expect(DEFAULT_BUSINESS_ROUTE.page).toBe(findRouteByKey("dashboard_today_sales")?.page);
    expect(DEFAULT_BUSINESS_PATH).toBe(DEFAULT_BUSINESS_ROUTE.page.path);
  });

  it("allows hidden routes, rejects disabled status, and identifies unknown paths", () => {
    expect(resolveRoute("/settings/personal-center").kind).toBe("allowed");
    expect(isRoutableStatus("disabled")).toBe(false);
    expect(resolveRoute("/not-in-navigation")).toEqual({ kind: "unknown" });
  });

  it("excludes hidden pages from the sidebar without copying metadata", () => {
    const settings = navigation.find((group) => group.key === "settings");
    if (!settings) throw new Error("Missing settings navigation group");

    expect(getSidebarPages(settings)).toEqual(
      settings.children.filter((page) => page.status !== "hidden"),
    );
  });
});

describe("tab workspace restoration", () => {
  const allowedPaths = navigation
    .flatMap((group) => group.children)
    .map((page) => page.path)
    .filter((path) => resolveRoute(path).kind === "allowed");

  it("falls back safely for missing, malformed, or unsupported storage", () => {
    const fallback = {
      version: TAB_WORKSPACE_VERSION,
      openPaths: [DEFAULT_BUSINESS_PATH],
      activePath: DEFAULT_BUSINESS_PATH,
    };

    expect(restoreTabWorkspace(null)).toEqual(fallback);
    expect(restoreTabWorkspace("not-json")).toEqual(fallback);
    expect(
      restoreTabWorkspace(
        JSON.stringify({
          version: TAB_WORKSPACE_VERSION + 1,
          openPaths: allowedPaths,
          activePath: allowedPaths[1],
        }),
      ),
    ).toEqual(fallback);
  });

  it("keeps only unique routable paths, injects Home, and validates activePath", () => {
    const hiddenPath = "/settings/personal-center";
    const otherPath = allowedPaths.find(
      (path) => path !== DEFAULT_BUSINESS_PATH && path !== hiddenPath,
    );
    if (!otherPath) throw new Error("Missing routable workspace fixture");

    const restored = restoreTabWorkspace(
      JSON.stringify({
        version: TAB_WORKSPACE_VERSION,
        openPaths: [otherPath, hiddenPath, otherPath, "/unknown"],
        activePath: "/unknown",
        title: "不得恢复",
        token: "不得恢复",
      }),
    );

    expect(restored).toEqual({
      version: TAB_WORKSPACE_VERSION,
      openPaths: [DEFAULT_BUSINESS_PATH, otherPath, hiddenPath],
      activePath: DEFAULT_BUSINESS_PATH,
    });
    expect(Object.keys(restored)).toEqual(["version", "openPaths", "activePath"]);
  });

  it("restores at most twelve tabs without evicting earlier paths", () => {
    const restored = restoreTabWorkspace(
      JSON.stringify({
        version: TAB_WORKSPACE_VERSION,
        openPaths: allowedPaths,
        activePath: allowedPaths[MAX_OPEN_TABS],
      }),
    );

    expect(restored.openPaths).toEqual(allowedPaths.slice(0, MAX_OPEN_TABS));
    expect(restored.openPaths).toHaveLength(MAX_OPEN_TABS);
    expect(restored.activePath).toBe(DEFAULT_BUSINESS_PATH);
  });
});
