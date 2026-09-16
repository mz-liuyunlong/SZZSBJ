export type SyncTaskModule = "商品" | "订单" | "广告" | "仓库" | "财务" | "售后";

export type SyncTaskStatus =
  | "成功"
  | "失败"
  | "运行中"
  | "部分成功"
  | "超时"
  | "已停用";

export type SyncTaskCycle = "日任务" | "周任务" | "手动任务";

export type SyncTaskTriggerType = "自动" | "手动" | "重试";

export type SyncScheduleTab = "day" | "week" | "weeklyOnly";

export interface SyncTaskFilters {
  module?: SyncTaskModule;
  status?: SyncTaskStatus;
  autoSync?: "on" | "off";
  keyword: string;
  anomalyOnly?: boolean;
}

export interface SyncTaskRow {
  id: string;
  interfaceId: string;
  taskName: string;
  interfaceName: string;
  provider: string;
  source: string | null;
  taskType: string;
  status: "enabled" | "disabled";
  module: SyncTaskModule;
  autoSync: boolean;
  frequency: string;
  nextRunAt?: string;
  lastStatus: SyncTaskStatus;
  lastRunAt: string | null;
  lastRunFinishedAt: string | null;
  todaySuccess: number;
  todayFailed: number;
  description: string;
  cycle: SyncTaskCycle;
  workItemsPlanned: number;
  workItemsSucceeded: number;
  workItemsFailed: number;
  recordsSeen: number;
  recordsWritten: number;
  errorCode: string | null;
  dryRun: boolean | null;
  updatedAt: string | null;
  dailyRunCount: number | null;
  runTimes: string[];
  weekDays: string[];
  timeoutSeconds: number | null;
  maxFailureTimes: number | null;
  duplicatePolicy: string | null;
  retryEnabled: boolean;
  retryTimes: number | null;
  retryInterval: string | null;
  notificationScenes: string[];
  notificationChannels: string[];
  notificationTargets: string | null;
}

export interface SyncTaskLog {
  id: string;
  taskId: string;
  runAt: string;
  triggerType: SyncTaskTriggerType;
  status: SyncTaskStatus;
  duration: string | null;
  total?: number;
  success?: number;
  failed?: number;
  requestId: string | null;
  errorSummary?: string | null;
}

export interface SyncTaskWorkItem {
  id: string;
  runId: string;
  ordinal: number;
  requestKind: string;
  status: string;
  attemptCount: number;
  requestSafeParams: Record<string, unknown>;
  responseCount: number | null;
  errorCode: string | null;
  errorMessage: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
}

export interface SyncTaskRawRequestRef {
  id: string;
  runId: string;
  workItemId: string;
  rawBlobId: string;
  requestKind: string;
  attemptNo: number;
  requestSafeParams: Record<string, unknown>;
  httpStatus: number | null;
  providerCode: string | null;
  isSuccess: boolean;
  responseCount: number | null;
  responseHash: string;
  payloadBytes: number;
  storageMode: "database" | "archive";
  archivePresent: boolean;
  requestedAt: string;
  receivedAt: string;
}

export interface SyncScheduleItem {
  id: string;
  time: string;
  taskName: string;
  module: SyncTaskModule;
  frequency: string;
  status: SyncTaskStatus;
  weekDay?: string;
}
