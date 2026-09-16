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

const WRITE_ACTION_NOT_OPEN = "真实操作写入入口尚未开放；需完成 Owner 授权、二次确认、审计日志和后端防重后再启用。";

const guard = (
  operation: SyncTaskOperationKey,
  reason: string,
  confirmTitle: string,
  confirmDescription: string,
): SyncTaskOperationGuard => ({
  operation,
  allowed: false,
  reason,
  confirmTitle,
  confirmDescription,
});

export function getManualSyncGuard(row: SyncTaskRow): SyncTaskOperationGuard {
  if (row.lastStatus === "运行中") {
    return guard(
      "manualSync",
      "任务运行中，不可重复触发。",
      "确认立即同步",
      "该任务正在运行，当前不允许重复触发。",
    );
  }

  if (row.status === "disabled") {
    return guard(
      "manualSync",
      "接口或同步配置未启用。",
      "确认立即同步",
      "该接口或同步配置未启用，不能发起真实同步。",
    );
  }

  return guard(
    "manualSync",
    WRITE_ACTION_NOT_OPEN,
    "确认立即同步",
    "后续启用后，这里需要展示任务名称、接口名称、影响范围、预计写入范围和审计记录。",
  );
}

export function getRetryGuard(row: SyncTaskRow): SyncTaskOperationGuard {
  if (!anomalyStatuses.has(row.lastStatus)) {
    return guard(
      "retry",
      "只有失败、超时或部分成功任务才允许重试。",
      "确认重试任务",
      "当前任务最近状态不属于可重试状态。",
    );
  }

  if (!row.retryEnabled) {
    return guard(
      "retry",
      "当前配置未开启重试。",
      "确认重试任务",
      "该任务配置未开启重试策略，不能发起真实重试。",
    );
  }

  return guard(
    "retry",
    WRITE_ACTION_NOT_OPEN,
    "确认重试任务",
    "后续启用后，这里需要展示失败原因、重试批次、重试次数、影响范围和审计记录。",
  );
}

export function getAutoSyncGuard(row: SyncTaskRow): SyncTaskOperationGuard {
  if (row.status === "disabled") {
    return guard(
      "autoSync",
      "接口或同步配置未启用。",
      "确认修改自动同步",
      "该接口或同步配置未启用，不能修改自动同步状态。",
    );
  }

  return guard(
    "autoSync",
    WRITE_ACTION_NOT_OPEN,
    "确认修改自动同步",
    "后续启用后，这里需要展示调度周期、下次运行时间、影响 Worker 和审计记录。",
  );
}

export function getSaveConfigGuard(row: SyncTaskRow): SyncTaskOperationGuard {
  if (row.status === "disabled") {
    return guard(
      "saveConfig",
      "接口或同步配置未启用。",
      "确认保存配置",
      "该接口或同步配置未启用，不能保存调度配置。",
    );
  }

  return guard(
    "saveConfig",
    WRITE_ACTION_NOT_OPEN,
    "确认保存配置",
    "后续启用后，这里需要展示配置差异、调度影响、通知对象和审计记录。",
  );
}
