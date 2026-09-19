/**
 * Central page preloader for heavy data pages.
 *
 * This warms API cache before the user opens a heavy table page.
 */
import dayjs from "dayjs";
import type { ProductManagementFilters } from "@/pages/products/productManagementTypes";
import {
  preloadProductManagementOptions,
  preloadProductManagementSkus,
  preloadProductManagementSummary,
} from "@/pages/products/productManagementApi";
import { preloadListingManagementRows } from "@/pages/products/listingManagementApi";
import { preloadDailySalesRows } from "@/pages/sales/dailySalesApi";
import { preloadOrderProfitSourceRecords } from "@/pages/sales/orderProfitApi";

type BrowserIdleApi = typeof globalThis & {
  requestIdleCallback?: (
    callback: () => void,
    options?: { timeout?: number },
  ) => number;
};

const idle = (callback: () => void) => {
  const runtime = globalThis as BrowserIdleApi;

  if (typeof runtime.requestIdleCallback === "function") {
    runtime.requestIdleCallback(callback, { timeout: 2_000 });
    return;
  }

  setTimeout(callback, 300);
};

const previousCompletedDay = () => dayjs().subtract(1, "day").format("YYYY-MM-DD");

const defaultProductManagementFilters = (): ProductManagementFilters => ({
  searchType: "sku",
  keyword: "",
  batchValues: [],
});

const preloadDefaultDailySales = () => {
  const day = previousCompletedDay();
  preloadDailySalesRows({ startDate: day, endDate: day, pageSize: 50 });
};

const preloadDefaultOrderProfit = () => {
  const day = previousCompletedDay();
  preloadOrderProfitSourceRecords({ startDate: day, endDate: day, pageSize: 50 });
};

const preloadDefaultListingManagement = () => {
  preloadListingManagementRows({ pageSize: 50 });
};

const preloadDefaultProductManagement = () => {
  const filters = defaultProductManagementFilters();
  preloadProductManagementOptions(filters);
  preloadProductManagementSummary(filters);
  preloadProductManagementSkus(filters, 1, 100);
};

export const preloadPageData = (path: string) => {
  if (path === "/sales/daily-sales") {
    preloadDefaultDailySales();
    return;
  }

  if (path === "/sales/order-profit") {
    preloadDefaultOrderProfit();
    return;
  }

  if (path === "/products/listing-management") {
    preloadDefaultListingManagement();
    return;
  }

  if (path === "/products/management") {
    preloadDefaultProductManagement();
  }
};

export const preloadNavigationGroupData = (groupKey: string) => {
  idle(() => {
    if (groupKey === "sales") {
      preloadDefaultDailySales();
      preloadDefaultOrderProfit();
      return;
    }

    if (groupKey === "products") {
      preloadDefaultProductManagement();
      preloadDefaultListingManagement();
    }
  });
};

export const preloadPrimaryPageData = () => {
  // Do not auto-preload heavy table APIs on app startup.
  // Heavy pages are warmed only from explicit navigation intent.
};
