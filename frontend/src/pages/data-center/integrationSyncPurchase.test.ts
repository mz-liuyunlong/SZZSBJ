/** Purchase folding must not change the other business tasks or account boundaries. */
import { afterEach, expect, it, vi } from "vitest";
import { backendRequest } from "@/api/backendApi";
import { listIntegrationSyncRunLogPage, listIntegrationSyncTasks } from "./integrationSyncTaskApi";

vi.mock("@/api/backendApi", () => ({ backendRequest: vi.fn() }));
afterEach(() => vi.resetAllMocks());

it("preserves purchase stage names when fetching paginated drawer logs", async () => {
  vi.mocked(backendRequest).mockResolvedValueOnce(envelope([
    { id: "parent", interface_key: "pmcPurchaseBoardSync", status: "failed" },
    { id: "child", interface_key: "purchasePlanList", status: "succeeded" },
  ]));
  const result = await listIntegrationSyncRunLogPage({ page: 1, pageSize: 20 });
  expect(result.items).toEqual([
    expect.objectContaining({ id: "parent", stageName: "完整流程" }),
    expect.objectContaining({ id: "child", stageName: "采购计划同步" }),
  ]);
});

const keys = ["pmcPurchaseBoardSync", "purchasePlanList", "purchaseOrderList", "purchaseReceiptOrderList", "walmartListingList"];
const interfaces = keys.map((key) => ({ id: key, interface_key: key, display_name: key,
  provider: "lingxing", request_kind: "offset_page", outbound_enabled: true }));
const config = (key: string, account = "fixture") => ({ id: `${key}:${account}`, interface_id: key,
  source_account_ref: account, is_enabled: true, schedule_enabled: key === "pmcPurchaseBoardSync",
  schedule_cron: key === "pmcPurchaseBoardSync" ? "0 */3 * * *" : null,
  max_pages: 1000, max_attempts: 3, page_size: 500, batch_size: null,
  next_run_at: null, updated_at: "2026-10-27T00:00:00Z" });
const envelope = (items: unknown[]) => ({ success: true, data: { items }, error: null,
  meta: {}, request_id: "synthetic" });
const dashboard = (latest_runs: unknown[]) => ({ success: true,
  data: { latest_runs, today_stats: [] }, error: null, meta: {}, request_id: "synthetic" });

it("shows one purchase task, preserves other businesses and folds historical source logs", async () => {
  vi.mocked(backendRequest)
    .mockResolvedValueOnce(envelope(interfaces))
    .mockResolvedValueOnce(envelope(keys.map((key) => config(key))))
    .mockResolvedValueOnce(dashboard([{ id: "historic", config_id: "purchasePlanList:fixture",
      interface_id: "purchasePlanList", interface_key: "purchasePlanList", source_account_ref: "fixture",
      trigger_type: "manual", status: "succeeded", queued_at: "2026-10-26T00:00:00Z",
      started_at: null, finished_at: null, records_seen: 3, work_items_succeeded: 1,
      work_items_failed: 0, request_id: "synthetic", error_code: null }]));
  const result = await listIntegrationSyncTasks();
  expect(result.rows.map((row) => row.taskName)).toEqual(["采购看板同步", "Listing 管理同步"]);
  expect(result.rows[0].scheduleCron).toBe("0 */3 * * *");
  expect(result.logs[0]).toMatchObject({ taskId: "pmcPurchaseBoardSync:fixture", stageName: "采购计划同步" });
});

it("does not hide another account's source tasks", async () => {
  vi.mocked(backendRequest)
    .mockResolvedValueOnce(envelope(interfaces))
    .mockResolvedValueOnce(envelope([...keys.map((key) => config(key)), config("purchasePlanList", "other")]))
    .mockResolvedValueOnce(dashboard([]));
  const result = await listIntegrationSyncTasks();
  expect(result.rows.find((row) => row.source === "other")).toMatchObject({ interfaceKey: "purchasePlanList" });
});

it("preserves legacy source rows when the unified task is not registered", async () => {
  vi.mocked(backendRequest)
    .mockResolvedValueOnce(envelope(interfaces.slice(1)))
    .mockResolvedValueOnce(envelope(keys.slice(1).map((key) => config(key))))
    .mockResolvedValueOnce(dashboard([]));
  expect((await listIntegrationSyncTasks()).rows).toHaveLength(4);
});

it("still lists interface tasks when dashboard is unavailable but sync-runs works", async () => {
  vi.mocked(backendRequest)
    .mockResolvedValueOnce(envelope(interfaces))
    .mockResolvedValueOnce(envelope([config("walmartListingList")]))
    .mockRejectedValueOnce(new Error("NOT_FOUND"))
    .mockResolvedValueOnce(envelope([]));
  const result = await listIntegrationSyncTasks();
  expect(result.rows.some((row) => row.interfaceKey === "walmartListingList")).toBe(true);
});

it("still lists interfaces when scoped config and dashboard calls fail", async () => {
  vi.mocked(backendRequest)
    .mockResolvedValueOnce(envelope(interfaces))
    .mockRejectedValueOnce(new Error("DATA_SCOPE_DENIED"))
    .mockRejectedValueOnce(new Error("DATA_SCOPE_DENIED"));
  const result = await listIntegrationSyncTasks();
  expect(result.rows.length).toBeGreaterThan(0);
  expect(result.rows.every((row) => row.lastStatus === "未执行" || row.lastStatus === "已停用")).toBe(true);
});
