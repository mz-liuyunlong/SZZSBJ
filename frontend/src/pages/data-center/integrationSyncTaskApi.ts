import { backendRequest } from "@/api/backendApi";
import type {
  SyncScheduleItem,
  SyncTaskLog,
  SyncTaskRow,
  SyncTaskStatus,
} from "@/pages/data-center/syncTaskTypes";

interface InterfaceDto {
  id: string;
  provider: string;
  interface_key: string;
  display_name: string;
  request_kind: string;
  outbound_enabled: boolean;
}
interface ConfigDto {
  id: string;
  interface_id: string;
  source_account_ref: string;
  is_enabled: boolean;
  schedule_enabled: boolean;
  schedule_cron: string | null;
  batch_size: number | null;
  page_size: number | null;
  max_pages: number | null;
  max_attempts: number;
  next_run_at: string | null;
  updated_at: string;
}
interface RunDto {
  id: string;
  config_id: string | null;
  interface_id: string;
  provider: string;
  interface_key: string;
  source_account_ref: string;
  trigger_type: string;
  status: string;
  request_id: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  work_items_total: number;
  work_items_succeeded: number;
  work_items_failed: number;
  records_seen: number;
  records_written: number;
  error_code: string | null;
  created_at: string;
}

const status: Record<string, SyncTaskStatus> = {
  succeeded: "成功",
  failed: "失败",
  running: "运行中",
  queued: "运行中",
  canceled: "已停用",
};
const trigger = (value: string): SyncTaskLog["triggerType"] => (
  value === "retry" ? "重试" : value === "schedule" ? "自动" : "手动"
);

const newestRun = (runs: RunDto[], interfaceId: string, accountRef?: string | null) => (
  runs.find((run) => run.interface_id === interfaceId
    && (accountRef === undefined || accountRef === null || run.source_account_ref === accountRef))
);

function row(
  item: InterfaceDto,
  config: ConfigDto | undefined,
  run: RunDto | undefined,
): SyncTaskRow {
  const lastStatus = run ? status[run.status] ?? "失败" : config?.is_enabled === false
    ? "已停用"
    : "已停用";
  return {
    id: config?.id ?? run?.id ?? item.id,
    interfaceId: item.id,
    interfaceName: item.display_name,
    provider: item.provider,
    source: config?.source_account_ref ?? run?.source_account_ref ?? null,
    taskType: item.request_kind,
    status: (config?.is_enabled ?? item.outbound_enabled) ? "enabled" : "disabled",
    taskName: item.display_name,
    module: "商品",
    autoSync: config?.schedule_enabled ?? false,
    frequency: config?.schedule_cron ?? "手动任务",
    nextRunAt: config?.next_run_at ?? undefined,
    lastStatus,
    lastRunAt: run?.started_at ?? run?.queued_at ?? null,
    lastRunFinishedAt: run?.finished_at ?? null,
    todaySuccess: run?.work_items_succeeded ?? 0,
    todayFailed: run?.work_items_failed ?? 0,
    workItemsPlanned: run?.work_items_total ?? 0,
    workItemsSucceeded: run?.work_items_succeeded ?? 0,
    workItemsFailed: run?.work_items_failed ?? 0,
    recordsSeen: run?.records_seen ?? 0,
    recordsWritten: run?.records_written ?? 0,
    errorCode: run?.error_code ?? null,
    dryRun: null,
    updatedAt: config?.updated_at ?? run?.created_at ?? null,
    description: item.display_name,
    cycle: config?.schedule_enabled ? "日任务" : "手动任务",
    dailyRunCount: null,
    runTimes: [],
    weekDays: [],
    timeoutSeconds: null,
    maxFailureTimes: config?.max_attempts ?? null,
    duplicatePolicy: null,
    retryEnabled: (config?.max_attempts ?? 1) > 1,
    retryTimes: config ? Math.max(config.max_attempts - 1, 0) : null,
    retryInterval: null,
    notificationScenes: [],
    notificationChannels: [],
    notificationTargets: null,
  };
}

export async function listIntegrationSyncTasks() {
  const [interfaces, configs, runs] = await Promise.all([
    backendRequest<{ items: InterfaceDto[] }>("/api/integrations/interfaces?page_size=100"),
    backendRequest<{ items: ConfigDto[] }>("/api/integrations/sync-configs?page_size=100"),
    backendRequest<{ items: RunDto[] }>("/api/integrations/sync-runs?page_size=100"),
  ]);
  const interfaceById = new Map(interfaces.data.items.map((item) => [item.id, item]));
  const rows = configs.data.items.flatMap((config) => {
    const item = interfaceById.get(config.interface_id);
    return item ? [row(item, config, newestRun(runs.data.items, item.id, config.source_account_ref))] : [];
  });
  for (const item of interfaces.data.items) {
    if (rows.some((candidate) => candidate.interfaceId === item.id)) continue;
    rows.push(row(item, undefined, newestRun(runs.data.items, item.id)));
  }
  const logs: SyncTaskLog[] = runs.data.items.map((run) => ({
    id: run.id,
    taskId: run.config_id ?? run.id,
    runAt: run.started_at ?? run.queued_at,
    triggerType: trigger(run.trigger_type),
    status: status[run.status] ?? "失败",
    duration: run.finished_at && run.started_at
      ? `${Math.max(Date.parse(run.finished_at) - Date.parse(run.started_at), 0)}ms`
      : null,
    total: run.records_seen,
    success: run.work_items_succeeded,
    failed: run.work_items_failed,
    requestId: run.request_id,
    errorSummary: run.error_code,
  }));
  const schedules: SyncScheduleItem[] = rows.flatMap((task) => task.nextRunAt ? [{
    id: task.id,
    time: task.nextRunAt,
    taskName: task.taskName,
    module: task.module,
    frequency: task.frequency,
    status: task.lastStatus,
  }] : []);
  return { rows, logs, schedules };
}
