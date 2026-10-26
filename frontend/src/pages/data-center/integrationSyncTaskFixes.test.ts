import { describe, expect, it } from "vitest";
import { foldProductDetailDependencyRows } from "@/pages/data-center/integrationSyncTaskApi";
import { buildSyncScheduleViews } from "@/pages/data-center/syncTaskScheduleViews";
import type { SyncTaskRow } from "@/pages/data-center/syncTaskTypes";

const row = (source: string, kind: string, state: SyncTaskRow["lastStatus"], runId: string): SyncTaskRow => ({
  id: `${source}-${kind}`,
  configId: `config-${source}-${kind}`,
  latestRunId: runId,
  scheduleCron: "0 0 * * *",
  backfillDays: 7,
  interfaceId: `iface-${kind}`,
  interfaceKey: kind,
  taskName: kind === "productList" ? "产品管理同步" : "产品详情同步",
  interfaceName: kind,
  provider: "lingxing",
  source,
  taskType: "offset_page",
  status: "enabled",
  module: "商品",
  autoSync: true,
  frequency: "0 0 * * *",
  nextRunAt: "2026-10-26T00:00:00Z",
  lastStatus: state,
  lastRunAt: "2026-10-26T00:00:00Z",
  lastRunFinishedAt: "2026-10-26T00:01:00Z",
  todaySuccess: 0, todayFailed: 0,
  todayRuns: 0,
  description: "",
  cycle: "日任务",
  workItemsPlanned: 1,
  workItemsSucceeded: state === "成功" ? 1 : 0,
  workItemsFailed: state === "失败" ? 1 : 0,
  recordsSeen: 0, recordsWritten: 0,
  errorCode: state === "失败" ? "SYNTHETIC_FAILURE" : null,
  dryRun: null, updatedAt: null,
  dailyRunCount: null, runTimes: [], weekDays: [], timeoutSeconds: null,
  maxFailureTimes: null, duplicatePolicy: null, retryEnabled: true,
  retryTimes: 2, retryInterval: null, notificationScenes: [],
  notificationChannels: [], notificationTargets: null,
});

describe("foldProductDetailDependencyRows", () => {
  it("folds only same-account dependencies and targets the failed child run", () => {
    const actual = foldProductDetailDependencyRows([
      row("a", "productList", "成功", "parent-a"),
      row("b", "productList", "成功", "parent-b"),
      row("a", "batchGetProductInfo", "失败", "child-a"),
      row("b", "batchGetProductInfo", "成功", "child-b"),
    ]);
    expect(actual).toHaveLength(2);
    expect(actual.find((item) => item.source === "a")?.latestRunId).toBe("child-a");
    expect(actual.find((item) => item.source === "a")?.lastStatus).toBe("失败");
    expect(actual.find((item) => item.source === "a")?.errorCode).toBe("SYNTHETIC_FAILURE");
    expect(actual.find((item) => item.source === "b")?.latestRunId).toBe("parent-b");
    expect(actual.find((item) => item.source === "b")?.lastStatus).toBe("成功");
  });

  it("keeps unmatched account child visible rather than folding across accounts", () => {
    const actual = foldProductDetailDependencyRows([
      row("a", "productList", "成功", "parent-a"),
      row("b", "batchGetProductInfo", "失败", "child-b"),
    ]);
    expect(actual).toHaveLength(2);
    expect(actual.find((item) => item.source === "b")?.latestRunId).toBe("child-b");
  });
});

describe("buildSyncScheduleViews", () => {
  it("separates today's occurrences and the next seven days", () => {
    const { day, week } = buildSyncScheduleViews([
      row("a", "productList", "成功", "parent-a"),
    ], new Date("2026-10-26T08:00:00Z"));
    expect(day).toHaveLength(1);
    expect(week).toHaveLength(7);
    expect(day[0].time).toBe("2026-10-26T00:00:00.000Z");
  });

  it("excludes disabled auto schedules", () => {
    const disabled = { ...row("a", "productList", "成功", "parent-a"), autoSync: false };
    expect(buildSyncScheduleViews([disabled], new Date("2026-10-26T08:00:00Z")).week).toHaveLength(0);
  });
});
