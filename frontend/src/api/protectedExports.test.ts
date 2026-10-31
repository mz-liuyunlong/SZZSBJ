// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { AUTH_TOKEN_STORAGE_KEY } from "@/pages/auth/authSession";
import { requestProductManagementExport } from "@/pages/products/productManagementApi";
import { exportListingManagementRows } from "@/pages/products/listingManagementApi";
import { downloadDailySalesExportCsv } from "@/pages/sales/dailySalesApi";
import { downloadOrderProfitExportCsv } from "@/pages/sales/orderProfitApi";
import {
  downloadOperationPlanFailedRows,
  downloadOperationPlanTemplate,
  importOperationPlans,
} from "@/api/operationPlansApi";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("protected exports", () => {
  it("uses the authenticated download path for all four protected CSV exports", async () => {
    const authToken = "synthetic-export-session-that-must-not-be-logged";
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, authToken);
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response("csv-content", {
      status: 200,
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="safe-export.csv"',
      },
    })));
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn().mockReturnValue("blob:synthetic-export"),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    await requestProductManagementExport({ searchType: "sku", keyword: "" }, ["sku"]);
    await exportListingManagementRows({}, ["sku"]);
    await downloadDailySalesExportCsv({ period: "day", dimension: "sku", columns: ["sales_amount"] });
    await downloadOrderProfitExportCsv({ period: "month", dimension: "msku", columns: ["sales_amount"] });

    expect(fetch).toHaveBeenCalledTimes(4);
    const expectedPaths = [
      "/api/product-management/skus/export?",
      "/api/listings/walmart/export?",
      "/api/sales/daily-sales/export?",
      "/api/sales/order-profit/export?",
    ];
    fetch.mock.calls.forEach(([path, init], index) => {
      expect(path).toEqual(expect.stringContaining(expectedPaths[index]));
      expect(init).toEqual(expect.objectContaining({
        headers: expect.objectContaining({ Authorization: `Bearer ${authToken}` }),
      }));
    });
  });

  it("sends large Listing batch exports in a POST body", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("csv-content", {
      status: 200,
      headers: { "Content-Type": "text/csv; charset=utf-8" },
    }));
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn().mockReturnValue("blob:synthetic-batch-export"),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    const batchValues = Array.from({ length: 1000 }, (_, index) => `synthetic-${index}`);
    await exportListingManagementRows({ batchValues, searchType: "sku" }, ["sku"]);

    expect(fetch).toHaveBeenCalledTimes(1);
    const [path, init] = fetch.mock.calls[0];
    expect(path).toBe("/api/listings/walmart/export/search");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body).batch_values).toEqual(batchValues);
  });

  it("uses the same authenticated path for operation-plan downloads and binary import", async () => {
    const authToken = "synthetic-operation-session-that-must-not-be-logged";
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, authToken);
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response("template", {
        status: 200,
        headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
      }))
      .mockResolvedValueOnce(new Response("failed-rows", {
        status: 200,
        headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        success: true,
        data: { batch_id: "synthetic-batch" },
        error: null,
        meta: null,
        request_id: "synthetic-request",
      }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn().mockReturnValue("blob:synthetic-operation-export"),
      revokeObjectURL: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    await downloadOperationPlanTemplate("month", "2026-10");
    await downloadOperationPlanFailedRows("synthetic-batch");
    await importOperationPlans({
      periodType: "month",
      periodKey: "2026-10",
      conflictPolicy: "skip_existing",
      file: new File(["synthetic"], "plans.xlsx"),
    });

    expect(fetch).toHaveBeenCalledTimes(3);
    fetch.mock.calls.forEach(([, init]) => {
      expect(init).toEqual(expect.objectContaining({
        headers: expect.objectContaining({ Authorization: `Bearer ${authToken}` }),
      }));
    });
    expect(fetch.mock.calls[2]?.[1]).toEqual(expect.objectContaining({
      method: "POST",
      body: expect.any(File),
      headers: expect.objectContaining({ "Content-Type": "application/octet-stream" }),
    }));
  });
});
