import type { SyncTaskRow, SyncTaskStatus } from "@/pages/data-center/syncTaskTypes";

export type SyncTaskOperationKey = "manualSync" | "retry" | "autoSync" | "saveConfig";

export interface SyncTaskOperationGuard {
  operation: SyncTaskOperationKey;
  allowed: boolean;
  reason: string;
  confirmTitle: string;
  confirmDescription: string;
}

const anomalyStatuses = new Set<SyncTaskStatus>(["失败", "超时", "部分成功"]);

const dataPagesInterfaceKeys = new Set([
  "getSellerList",
  "walmartListingList",
  "saleStatPageList",
  "orderV2List",
  "walmartReturnOrderList",
  "walmartAdvertiserList",
  "walmartAdItemSpList",
]);

const executableDataPagesInterfaceKeys = new Set([
  "walmartListingList",
  "saleStatPageList",
  "walmartReturnOrderList",
  "walmartAdItemSpList",
])

const nonExecutableDataPagesReason = "该接口是 Data Pages 总同步的组成接口，不单独配置定时任务。请配置「Listing 管理同步」「每日销售同步」「退款退货同步」或「广告报表同步」。";

const isNonExecutableDataPagesTask = (row: SyncTaskRow) => (
  dataPagesInterfaceKeys.has(row.interfaceKey)
  && !executableDataPagesInterfaceKeys.has(row.interfaceKey)
);

const guard = (
  operation: SyncTaskOperationKey,
  allowed: boolean,
  reason: string,
  confirmTitle: string,
  confirmDescription: string,
): SyncTaskOperationGuard => ({
  operation,
  allowed,
  reason,
  confirmTitle,
  confirmDescription,
});

export function getManualSyncGuard(row: SyncTaskRow): SyncTaskOperationGuard {
  if (isNonExecutableDataPagesTask(row)) {
    return guard(
      "manualSync",
      false,
      nonExecutableDataPagesReason,
      "确认立即同步",
      "该接口不作为独立生产同步任务执行。",
    );
  }

  if (!row.configId) {
    return guard(
      "manualSync",
      false,
      "当前任务缺少同步配置，不能发起真实同步。",
      "确认立即同步",
      "该任务没有可执行的同步配置 ID。",
    );
  }

  if (row.lastStatus === "运行中") {
    return guard(
      "manualSync",
      false,
      "任务运行中，不可重复触发。",
      "确认立即同步",
      "该任务正在运行，当前不允许重复触发。",
    );
  }

  if (row.status === "disabled") {
    return guard(
      "manualSync",
      false,
      "同步配置未启用，请先进入配置页保存一次任务配置。",
      "确认立即同步",
      "该任务当前未启用，不能直接发起真实同步。",
    );
  }

  return guard(
    "manualSync",
    true,
    "可发起真实同步，执行前必须二次确认。",
    "确认立即同步",
    "确认后会创建真实同步运行记录，并尝试派发后台 Worker 执行。",
  );
}

export function getRetryGuard(row: SyncTaskRow): SyncTaskOperationGuard {
  if (isNonExecutableDataPagesTask(row)) {
    return guard(
      "retry",
      false,
      nonExecutableDataPagesReason,
      "确认重试任务",
      "该接口不作为独立生产同步任务执行。",
    );
  }

  if (!row.latestRunId) {
    return guard(
      "retry",
      false,
      "当前任务没有最近执行记录，不能重试。",
      "确认重试任务",
      "该任务缺少可重试的 run_id。",
    );
  }

  if (!anomalyStatuses.has(row.lastStatus)) {
    return guard(
      "retry",
      false,
      "只有失败、超时或部分成功任务才允许重试。",
      "确认重试任务",
      "当前任务最近状态不属于可重试状态。",
    );
  }

  if (!row.retryEnabled) {
    return guard(
      "retry",
      false,
      "当前配置未开启重试。",
      "确认重试任务",
      "该任务配置未开启重试策略，不能发起真实重试。",
    );
  }

  return guard(
    "retry",
    true,
    "可发起真实重试，执行前必须二次确认。",
    "确认重试任务",
    "确认后会基于最近失败运行创建真实重试任务，并尝试派发后台 Worker 执行。",
  );
}

export function getAutoSyncGuard(row: SyncTaskRow, checked: boolean): SyncTaskOperationGuard {
  if (isNonExecutableDataPagesTask(row)) {
    return guard(
      "autoSync",
      false,
      nonExecutableDataPagesReason,
      "确认修改自动同步",
      "该接口不作为独立生产同步任务执行。",
    );
  }

  if (!row.configId) {
    return guard(
      "autoSync",
      false,
      "当前任务缺少同步配置，不能修改自动同步。",
      "确认修改自动同步",
      "该任务没有可写入的同步配置 ID。",
    );
  }

  if (checked && !row.scheduleCron) {
    return guard(
      "autoSync",
      false,
      "当前任务缺少同步计划，请先在配置中设置执行时间。",
      "确认修改自动同步",
      "请先在配置里设置日任务或周任务执行时间，再开启自动同步。",
    );
  }

  return guard(
    "autoSync",
    true,
    checked ? "可开启自动同步，执行前必须二次确认。" : "可关闭自动同步，执行前必须二次确认。",
    checked ? "确认开启自动同步" : "确认关闭自动同步",
    checked
      ? "确认后会写入调度配置，后续由后端 Scheduler 自动触发。"
      : "确认后会关闭该任务自动调度，不影响手动同步。",
  );
}

export function getSaveConfigGuard(row: SyncTaskRow): SyncTaskOperationGuard {
  if (isNonExecutableDataPagesTask(row)) {
    return guard(
      "saveConfig",
      false,
      nonExecutableDataPagesReason,
      "确认保存配置",
      "该接口不作为独立生产同步任务执行。",
    );
  }

  if (!row.configId) {
    return guard(
      "saveConfig",
      false,
      "当前任务缺少同步配置，不能保存。",
      "确认保存配置",
      "该任务没有可写入的同步配置 ID。",
    );
  }

  return guard(
    "saveConfig",
    true,
    "可保存配置，执行前必须二次确认。",
    "确认保存配置",
    "确认后会写入同步配置，包括启用任务、自动同步、cron 计划和重试次数。",
  );
}
