/** Actual existing governance routes used by the purchase pipeline; no external endpoint. */
import type { ApiDocItem, ApiDocModule } from "./apiDocsTypes";

const operations: Array<Pick<ApiDocItem, "id" | "method" | "title" | "path" | "authScope" | "bodyParams">> = [
  { id: "purchase-sync-run", method: "POST", title: "采购看板完整同步", path: "/api/integrations/sync-configs/{id}/run", authScope: "integrations:execute",
    bodyParams: [{ name: "reason", type: "string", required: true, description: "运行原因" }, { name: "idempotency_key", type: "string", required: false, description: "请求幂等键" }] },
  { id: "purchase-sync-config", method: "PATCH", title: "采购看板三小时调度配置", path: "/api/integrations/sync-configs/{id}", authScope: "integrations:update",
    bodyParams: [{ name: "is_enabled", type: "boolean", required: false, description: "允许任务执行" }, { name: "schedule_enabled", type: "boolean", required: false, description: "自动同步开关" }, { name: "schedule_cron", type: "string", required: false, description: "开启自动同步时必填；每三小时为 0 */3 * * *，UTC" }] },
  { id: "purchase-sync-retry", method: "POST", title: "采购看板失败任务重试", path: "/api/integrations/sync-runs/{id}/retry", authScope: "integrations:execute",
    bodyParams: [{ name: "reason", type: "string", required: true, description: "重试原因，原失败窗口完整重跑" }] },
  { id: "purchase-sync-stages", method: "GET", title: "采购同步阶段日志", path: "/api/integrations/sync-runs/{id}/work-items", authScope: "integrations:read", bodyParams: [] },
];

export const purchaseSyncApiDocs: ApiDocModule = {
  key: "pmc_purchase_sync", name: "采购看板同步", icon: "🔄", desc: "一个入口完成采集、清洗和看板刷新",
  levels: [{ name: "同步任务", desc: "复用受保护的同步治理接口，source-account 范围隔离", apis: operations.map((operation) => ({
    ...operation, moduleKey: "pmc_purchase_sync", moduleName: "采购看板同步", levelName: "同步任务", levelDesc: "手动和自动共用完整流程",
    purpose: "父任务 pmcPurchaseBoardSync；三个来源成功后发布 DWD/DWS，只有整链成功才推进水位。",
    requestMode: operation.method === "GET" ? "Query" : "JSON Body", scenario: "数据中心 → 任务中心 → 采购看板同步",
    successReturn: "success/data/error/meta/request_id；运行接口202返回排队状态，非采集完成。",
    authScope: `${operation.authScope}；可信 source-account scope`,
    queryParams: operation.method === "GET" ? [{ name: "page_size", type: "integer", required: false, description: "分页大小，最多100" }] : [],
    returnFields: [{ name: "data", type: "object", required: true, description: "配置记录 / 新run_id及queued状态 / 工作项列表；详见docs/api/pmc-purchase-unified-sync.md" }],
    requestExample: { method: operation.method, path: operation.path, ...(operation.method === "PATCH" ? { body: { is_enabled: true, schedule_enabled: true, schedule_cron: "0 */3 * * *" } } : operation.method === "POST" ? { body: { reason: "人工确认同步采购看板" } } : {}) },
    responseExample: { success: false, data: null, error: { code: "NOT_FOUND" }, meta: null, request_id: "synthetic-out-of-scope-example" },
  })) }],
};
