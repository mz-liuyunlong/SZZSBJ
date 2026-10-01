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

const hiddenStandaloneInterfaceKeys = new Set([
  "getSellerList",
  "orderV2List",
  "walmartAdvertiserList",
]);

const shouldDisplayTaskRow = (task: SyncTaskRow) => (
  !hiddenStandaloneInterfaceKeys.has(task.interfaceKey)
);


const dataPagesInterfaceKeys = new Set([
  "getSellerList",
  "walmartListingList",
  "saleStatPageList",
  "orderV2List",
  "walmartReturnOrderList",
  "walmartAdvertiserList",
  "walmartAdItemSpList",
]);

const pmcPurchaseInterfaceKeys = new Set([
  "purchasePlanList",
  "purchaseOrderList",
  "purchaseReceiptOrderList",
]);

const moduleForInterface = (item: InterfaceDto): SyncTaskRow["module"] => {
  if (dataPagesInterfaceKeys.has(item.interface_key)) {
    if (
      item.interface_key === "walmartAdvertiserList"
      || item.interface_key === "walmartAdItemSpList"
    ) {
      return "广告";
    }

    if (item.interface_key === "walmartReturnOrderList") {
      return "售后";
    }

    if (
      item.interface_key === "saleStatPageList"
      || item.interface_key === "orderV2List"
    ) {
      return "订单";
    }

    return "商品";
  }

  if (pmcPurchaseInterfaceKeys.has(item.interface_key)) return "仓库";
  if (item.interface_key === "productList" || productDetailDependencyKeys.has(item.interface_key)) return "商品";

  return "商品";
};


const chineseTaskNames: Record<string, string> = {
  getSellerList: "店铺列表同步",
  walmartListingList: "Listing 管理同步",
  saleStatPageList: "每日销售同步",
  orderV2List: "订单明细同步",
  walmartReturnOrderList: "退款退货同步",
  walmartAdvertiserList: "广告账户同步",
  walmartAdItemSpList: "广告报表同步",
  productList: "产品管理同步",
  batchGetProductInfo: "产品详情同步",
  purchasePlanList: "采购计划同步",
  purchaseOrderList: "采购单同步",
  purchaseReceiptOrderList: "采购入库同步",
};

const chineseInterfaceNames: Record<string, string> = {
  getSellerList: "领星店铺列表接口",
  walmartListingList: "沃尔玛 Listing 列表接口",
  saleStatPageList: "沃尔玛销售统计接口",
  orderV2List: "沃尔玛订单明细接口",
  walmartReturnOrderList: "沃尔玛退款退货接口",
  walmartAdvertiserList: "沃尔玛广告账户接口",
  walmartAdItemSpList: "沃尔玛广告商品报表接口",
  productList: "领星产品列表接口",
  batchGetProductInfo: "领星产品详情接口",
  purchasePlanList: "领星采购计划接口",
  purchaseOrderList: "领星采购单接口",
  purchaseReceiptOrderList: "领星采购入库接口",
};

const descriptionForInterface = (item: InterfaceDto) => {
  if (item.interface_key === "productList") {
    return "前端只显示一个产品管理同步任务：同步 ProductList、ProductInfo，并刷新产品管理当前数据。";
  }

  if (item.interface_key === "walmartListingList") {
    return "前端可配置的 Listing 管理同步：同步店铺与 Listing，并刷新 Listing 管理 MART；不按日期回刷。";
  }

  if (item.interface_key === "saleStatPageList") {
    return "前端可配置的每日销售同步：同步销售统计与订单明细，可按美国业务日期回刷最近几天。";
  }

  if (item.interface_key === "walmartReturnOrderList") {
    return "前端可配置的退款退货同步：同步退款退货数据，可按美国业务日期回刷最近几天。";
  }

  if (item.interface_key === "walmartAdItemSpList") {
    return "前端可配置的广告报表同步：同步广告账户与广告报表，可按美国业务日期回刷最近几天。";
  }

  if (
    item.interface_key === "getSellerList"
    || item.interface_key === "orderV2List"
    || item.interface_key === "walmartAdvertiserList"
  ) {
    return "组成接口，不单独配置定时任务；由对应业务同步任务统一执行。";
  }

  if (productDetailDependencyKeys.has(item.interface_key)) {
    return "ProductInfo 依赖 ProductList 的 active Product ID，前端合并到产品管理同步展示。";
  }

  if (pmcPurchaseInterfaceKeys.has(item.interface_key)) {
    return "PMC 采购接口需后端治理配置启用后才能执行。";
  }

  return item.display_name;
};


const taskNameForInterface = (item: InterfaceDto) => (
  chineseTaskNames[item.interface_key] ?? item.display_name
);

const interfaceNameForInterface = (item: InterfaceDto) => (
  chineseInterfaceNames[item.interface_key] ?? item.display_name
);


const isProductListTask = (task: SyncTaskRow) => {
  const key = task.interfaceKey.toLowerCase();
  const name = task.interfaceName.toLowerCase();

  return productListInterfaceKeys.has(task.interfaceKey)
    || key.includes("productlist")
    || name.includes("productlist")
    || task.taskName.includes("产品管理")
    || task.taskName.includes("产品列表");
};

const isProductDetailDependencyTask = (task: SyncTaskRow) => {
  const key = task.interfaceKey.toLowerCase();
  const name = task.interfaceName.toLowerCase();

  return productDetailDependencyKeys.has(task.interfaceKey)
    || key.includes("batchgetproductinfo")
    || key.includes("productinfo")
    || (name.includes("batch") && name.includes("product info"))
    || task.taskName.includes("产品详情");
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
  description: "ProductList 与 ProductInfo 合并展示为一个产品管理同步任务。",
});

const foldProductDetailDependencyRows = (rows: SyncTaskRow[]): SyncTaskRow[] => {
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
    backfillDays: config?.max_pages ?? null,
    interfaceId: item.id,
    interfaceKey: item.interface_key,
    interfaceName: interfaceNameForInterface(item),
    provider: item.provider,
    source: config?.source_account_ref ?? run?.source_account_ref ?? null,
    taskType: item.request_kind,
    status: (config?.is_enabled ?? item.outbound_enabled) ? "enabled" : "disabled",
    taskName: taskNameForInterface(item),
    module: moduleForInterface(item),
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
    description: descriptionForInterface(item),
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
  const visibleRows = foldProductDetailDependencyRows(rows).filter(shouldDisplayTaskRow);
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
