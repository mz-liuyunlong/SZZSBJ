import { describe, expect, it } from "vitest";
import {
  getAutoSyncGuard,
  getManualSyncGuard,
  getRetryGuard,
  getSaveConfigGuard,
} from "@/pages/data-center/syncTaskOperationGuards";
import type { SyncTaskRow } from "@/pages/data-center/syncTaskTypes";

const baseTask = {
  id: "task-1",
  configId: "config-1",
  latestRunId: "run-1",
  scheduleCron: "0 8 * * *",
  interfaceId: "interface-1",
  interfaceKey: "productList",
  taskName: "Lingxing ProductList",
  interfaceName: "productList",
  provider: "lingxing",
  source: null,
  taskType: "one_time",
  status: "enabled",
  module: "商品",
  autoSync: false,
  frequency: "0 8 * * *",
  nextRunAt: undefined,
  lastStatus: "成功",
  lastRunAt: null,
  lastRunFinishedAt: null,
  todaySuccess: 0,
  todayFailed: 0,
  description: "ProductList sync",
  cycle: "手动任务",
  workItemsPlanned: 0,
  workItemsSucceeded: 0,
  workItemsFailed: 0,
  recordsSeen: 0,
  recordsWritten: 0,
  errorCode: null,
  dryRun: null,
  updatedAt: null,
  dailyRunCount: null,
  runTimes: [],
  weekDays: [],
  timeoutSeconds: null,
  maxFailureTimes: null,
  duplicatePolicy: null,
  retryEnabled: true,
  retryTimes: null,
  retryInterval: null,
  notificationScenes: [],
  notificationChannels: [],
  notificationTargets: null,
} satisfies SyncTaskRow;

describe("syncTaskOperationGuards", () => {
  it("allows manual sync when the task has a writable config and is not running", () => {
    const result = getManualSyncGuard(baseTask);
    expect(result.allowed).toBe(true);
    expect(result.reason).toContain("可发起真实同步");
  });

  it("blocks manual sync without config or while running", () => {
    expect(getManualSyncGuard({ ...baseTask, configId: null }).allowed).toBe(false);
    expect(getManualSyncGuard({ ...baseTask, configId: null }).reason).toContain("缺少同步配置");
    expect(getManualSyncGuard({ ...baseTask, lastStatus: "运行中" }).allowed).toBe(false);
    expect(getManualSyncGuard({ ...baseTask, lastStatus: "运行中" }).reason).toContain("运行中");
  });

  it("allows retry only for anomaly statuses with a latest run", () => {
    expect(getRetryGuard(baseTask).allowed).toBe(false);
    expect(getRetryGuard(baseTask).reason).toContain("只有失败");

    const failedResult = getRetryGuard({ ...baseTask, lastStatus: "失败" });
    expect(failedResult.allowed).toBe(true);
    expect(failedResult.reason).toContain("可发起真实重试");

    expect(getRetryGuard({ ...baseTask, lastStatus: "失败", latestRunId: null }).allowed).toBe(false);
  });

  it("guards auto sync and config save with writable config requirements", () => {
    expect(getAutoSyncGuard(baseTask, true).allowed).toBe(true);
    expect(getAutoSyncGuard({ ...baseTask, scheduleCron: null }, true).allowed).toBe(false);
    expect(getAutoSyncGuard(baseTask, false).allowed).toBe(true);
    expect(getSaveConfigGuard(baseTask).allowed).toBe(true);
    expect(getSaveConfigGuard({ ...baseTask, configId: null }).allowed).toBe(false);
  });
});
