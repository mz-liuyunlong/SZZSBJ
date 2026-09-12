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
  taskName: string;
  interfaceName: string;
  module: SyncTaskModule;
  autoSync: boolean;
  frequency: string;
  nextRunAt?: string;
  lastStatus: SyncTaskStatus;
  lastRunAt: string;
  todaySuccess: number;
  todayFailed: number;
  description: string;
  cycle: SyncTaskCycle;
  dailyRunCount: number;
  runTimes: string[];
  weekDays: string[];
  timeoutSeconds: number;
  maxFailureTimes: number;
  duplicatePolicy: string;
  retryEnabled: boolean;
  retryTimes: number;
  retryInterval: string;
  notificationScenes: string[];
  notificationChannels: string[];
  notificationTargets: string;
}

export interface SyncTaskLog {
  id: string;
  taskId: string;
  runAt: string;
  triggerType: SyncTaskTriggerType;
  status: SyncTaskStatus;
  duration: string;
  total?: number;
  success?: number;
  failed?: number;
  requestId: string;
  errorSummary?: string;
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
