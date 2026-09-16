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
  interfaceId: "interface-1",
  taskName: "Lingxing ProductList",
  interfaceName: "productList",
  provider: "lingxing",
  source: null,
  taskType: "one_time",
  status: "enabled",
  module: "商品",
  autoSync: false,
  frequency: "手动任务",
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
  it("keeps manual sync write action closed before real operation wiring", () => {
    expect(getManualSyncGuard(baseTask).allowed).toBe(false);
    expect(getManualSyncGuard(baseTask).reason).toContain("真实操作写入入口尚未开放");
  });

  it("blocks duplicate manual sync while task is running", () => {
    expect(getManualSyncGuard({ ...baseTask, lastStatus: "运行中" }).reason).toContain("运行中");
  });

  it("only allows retry planning for anomaly statuses, while keeping write action closed", () => {
    expect(getRetryGuard(baseTask).reason).toContain("只有失败");
    expect(getRetryGuard({ ...baseTask, lastStatus: "失败" }).allowed).toBe(false);
  });

  it("keeps auto sync and config save write actions closed", () => {
    expect(getAutoSyncGuard(baseTask).allowed).toBe(false);
    expect(getSaveConfigGuard(baseTask).allowed).toBe(false);
  });
});
