import { describe, expect, it } from "vitest";
import { navigation } from "../config/navigation";
import {
  DEFAULT_BUSINESS_PATH,
  DEFAULT_BUSINESS_ROUTE,
  findRouteByKey,
  getSidebarPages,
  isRoutableStatus,
  resolveRoute,
} from "./routeResolver";

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
