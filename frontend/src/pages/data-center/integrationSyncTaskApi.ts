import { backendRequest } from "@/api/backendApi";
import type {
  SyncScheduleItem,
  SyncTaskLog,
  SyncTaskRawRequestRef,
  SyncTaskWorkItem,
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


interface WorkItemDto {
  id: string;
  run_id: string;
  ordinal: number;
  request_kind: string;
  status: string;
  attempt_count: number;
  request_safe_params: Record<string, unknown>;
  response_count: number | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

interface SyncRunCreatedDto {
  run_id: string;
  trigger_type: string;
  status: string;
  retry_of_run_id: string | null;
}

export interface SyncConfigUpdatePayload {
  is_enabled?: boolean;
  schedule_enabled?: boolean;
  schedule_cron?: string | null;
  page_size?: number | null;
  batch_size?: number | null;
  max_pages?: number | null;
  max_attempts?: number | null;
  retention_policy_id?: string | null;
}

interface RawRequestMetadataDto {
  id: string;
  run_id: string;
  work_item_id: string;
  raw_blob_id: string;
  request_kind: string;
  attempt_no: number;
  request_safe_params: Record<string, unknown>;
  http_status: number | null;
  provider_code: string | null;
  is_success: boolean;
  response_count: number | null;
  response_hash: string;
  payload_bytes: number;
  storage_mode: "database" | "archive";
  archive_present: boolean;
  requested_at: string;
  received_at: string;
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


const productListInterfaceKeys = new Set([
  "productList",
  "listProduct",
  "product_list",
]);

const productDetailDependencyKeys = new Set([
  "batchGetProductInfo",
  "batchProductInfo",
  "getProductInfo",
  "productInfo",
]);

const isProductListTask = (task: SyncTaskRow) => {
  const key = task.interfaceKey.toLowerCase();
  const name = task.interfaceName.toLowerCase();
  return productListInterfaceKeys.has(task.interfaceKey)
    || key.includes("productlist")
    || name.includes("productlist");
};

const isProductDetailDependencyTask = (task: SyncTaskRow) => {
  const key = task.interfaceKey.toLowerCase();
  const name = task.interfaceName.toLowerCase();
  return productDetailDependencyKeys.has(task.interfaceKey)
    || key.includes("batchgetproductinfo")
    || (name.includes("batch") && name.includes("product info"));
};

const latestDate = (...values: Array<string | null | undefined>) => (
  values
    .filter((value): value is string => Boolean(value))
    .sort((left, right) => Date.parse(right) - Date.parse(left))[0] ?? null
);

const statusPriority: Record<SyncTaskStatus, number> = {
  已停用: 0,
  成功: 1,
  运行中: 2,
  部分成功: 3,
  超时: 4,
  失败: 5,
};

const worseStatus = (left: SyncTaskStatus, right: SyncTaskStatus) => (
  statusPriority[right] > statusPriority[left] ? right : left
);

const mergeProductDetailDependency = (
  parent: SyncTaskRow,
  dependency: SyncTaskRow,
): SyncTaskRow => ({
  ...parent,
  todaySuccess: parent.todaySuccess + dependency.todaySuccess,
  todayFailed: parent.todayFailed + dependency.todayFailed,
  workItemsPlanned: parent.workItemsPlanned + dependency.workItemsPlanned,
  workItemsSucceeded: parent.workItemsSucceeded + dependency.workItemsSucceeded,
  workItemsFailed: parent.workItemsFailed + dependency.workItemsFailed,
  recordsSeen: parent.recordsSeen + dependency.recordsSeen,
  recordsWritten: parent.recordsWritten + dependency.recordsWritten,
  lastStatus: worseStatus(parent.lastStatus, dependency.lastStatus),
  lastRunAt: latestDate(parent.lastRunAt, dependency.lastRunAt),
  lastRunFinishedAt: latestDate(parent.lastRunFinishedAt, dependency.lastRunFinishedAt),
  updatedAt: latestDate(parent.updatedAt, dependency.updatedAt),
  errorCode: parent.errorCode ?? dependency.errorCode,
  description: "ProductList 与产品详情依赖同步合并展示；详情步骤依赖 Product ID，不单独展示为前端任务。",
});

const foldProductDetailDependencyRows = (rows: SyncTaskRow[]) => {
  const dependencies = rows.filter(isProductDetailDependencyTask);
  if (dependencies.length === 0) return rows;

  const productList = rows.find(isProductListTask);
  if (!productList) {
    return rows.filter((task) => !isProductDetailDependencyTask(task));
  }

  const mergedProductList = dependencies.reduce(
    mergeProductDetailDependency,
    productList,
  );

  return rows.flatMap((task) => {
    if (isProductDetailDependencyTask(task)) return [];
    if (task === productList) return [mergedProductList];
    return [task];
  });
};


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
    configId: config?.id ?? run?.config_id ?? null,
    latestRunId: run?.id ?? null,
    scheduleCron: config?.schedule_cron ?? null,
    interfaceId: item.id,
    interfaceKey: item.interface_key,
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
  const visibleRows = foldProductDetailDependencyRows(rows);
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
  const schedules: SyncScheduleItem[] = visibleRows.flatMap((task) => task.nextRunAt ? [{
    id: task.id,
    time: task.nextRunAt,
    taskName: task.taskName,
    module: task.module,
    frequency: task.frequency,
    status: task.lastStatus,
  }] : []);
  return { rows: visibleRows, logs, schedules };
}


function workItem(item: WorkItemDto): SyncTaskWorkItem {
  return {
    id: item.id,
    runId: item.run_id,
    ordinal: item.ordinal,
    requestKind: item.request_kind,
    status: item.status,
    attemptCount: item.attempt_count,
    requestSafeParams: item.request_safe_params,
    responseCount: item.response_count,
    errorCode: item.error_code,
    errorMessage: item.error_message,
    startedAt: item.started_at,
    finishedAt: item.finished_at,
    createdAt: item.created_at,
  };
}

function rawRequestRef(item: RawRequestMetadataDto): SyncTaskRawRequestRef {
  return {
    id: item.id,
    runId: item.run_id,
    workItemId: item.work_item_id,
    rawBlobId: item.raw_blob_id,
    requestKind: item.request_kind,
    attemptNo: item.attempt_no,
    requestSafeParams: item.request_safe_params,
    httpStatus: item.http_status,
    providerCode: item.provider_code,
    isSuccess: item.is_success,
    responseCount: item.response_count,
    responseHash: item.response_hash,
    payloadBytes: item.payload_bytes,
    storageMode: item.storage_mode,
    archivePresent: item.archive_present,
    requestedAt: item.requested_at,
    receivedAt: item.received_at,
  };
}

export async function listIntegrationSyncRunWorkItems(runId: string) {
  const response = await backendRequest<{ items: WorkItemDto[] }>(
    `/api/integrations/sync-runs/${runId}/work-items?page_size=100`,
  );
  return response.data.items.map(workItem);
}

export async function listIntegrationSyncRunRawRequestRefs(runId: string) {
  const response = await backendRequest<{ items: RawRequestMetadataDto[] }>(
    `/api/integrations/sync-runs/${runId}/raw-request-refs?page_size=100`,
  );
  return response.data.items.map(rawRequestRef);
}

const idempotencyKey = (operation: string, id: string) => (
  `frontend:${operation}:${id}:${Date.now()}`
);

export async function createIntegrationSyncManualRun(configId: string, reason: string) {
  const response = await backendRequest<SyncRunCreatedDto>(
    `/api/integrations/sync-configs/${configId}/run`,
    {
      method: "POST",
      body: JSON.stringify({
        reason,
        idempotency_key: idempotencyKey("manual-run", configId),
      }),
    },
  );
  return response.data;
}

export async function retryIntegrationSyncRun(runId: string, reason: string) {
  const response = await backendRequest<SyncRunCreatedDto>(
    `/api/integrations/sync-runs/${runId}/retry`,
    {
      method: "POST",
      body: JSON.stringify({
        reason,
        idempotency_key: idempotencyKey("retry-run", runId),
      }),
    },
  );
  return response.data;
}

export async function updateIntegrationSyncConfig(
  configId: string,
  payload: SyncConfigUpdatePayload,
) {
  const response = await backendRequest<ConfigDto>(
    `/api/integrations/sync-configs/${configId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
  return response.data;
}
