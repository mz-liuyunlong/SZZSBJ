/** Actual WFS preparation endpoints; examples are empty and never invoke external systems. */
import type { ApiDocItem, ApiDocModule, ApiMethod } from "./apiDocsTypes";
const endpoints: [ApiMethod, string, string][] = [
  ["GET", "/orders", "待发货打包单列表"], ["GET", "/summary", "待发货打包单统计"],
  ["GET", "/filter-options", "待发货店铺选项（dim_lingxing_stores）"], ["GET", "/orders/{id}", "待发货单据详情"],
  ["GET", "/orders/{id}/identity-options", "同 SKU 目标商品身份"],
  ["POST", "/orders/{id}/identity", "换店铺或链接并生成新 PK"],
  ["GET", "/capabilities", "创建能力"],
  ["POST", "/allocation-preview", "按箱数分票核对"],
  ["POST", "/creation-operations", "自动审批并提交创建"],
  ["GET", "/creation-operations", "查询创建记录"],
  ["GET", "/creation-operations/{ident}", "创建结果详情"],
  ["POST", "/creation-operations/{ident}/reconcile", "核实结果"],
  ["POST", "/creation-operations/{ident}/labels/retry", "补取箱唛"],
  ["GET", "/creation-operations/{ident}/labels/{shipment_id}", "下载箱唛PDF"],
  ["POST", "/optional-previews", "按需探测"],
  ["POST", "/drafts", "生成待审批货件草稿"], ["GET", "/drafts/{id}", "读取草稿回执"],
];
const apis: ApiDocItem[] = endpoints.map(([method, suffix, title]) => ({
  id: `pmc-wfs-pending-${method}-${suffix}`, moduleKey: "pmc-wfs", moduleName: "PMC WFS",
  levelName: "待发货打包单", levelDesc: "本系统装箱、按箱数创建及结果；真实平台适配器尚未启用", method, title,
  path: `/api/pmc/wfs/pending-packing${suffix}`, purpose: title,
  requestMode: method === "GET" ? "Query / 无 Body" : "JSON Body；详细类型与示例见 OpenAPI 和 WFS API 文档",
  successReturn: "{success,data,error,meta,request_id}", scenario: "待发货打包单页面真实接口",
  authScope: "page:pmc:wfs:view；独立动作 permissionKey；来源账号及店铺数据范围",
  queryParams: suffix === "/orders" || suffix === "/summary" ? [
    { name: "store_id", type: "string", required: false, description: "目标店铺ID" },
    { name: "keyword", type: "string", required: false, description: "PK、SKU、ItemID、GTIN、MSKU" },
    { name: "only_test", type: "boolean", required: false, description: "仅业务测试记录" },
  ] : [],
  bodyParams: method === "POST" && (suffix === "/drafts" || suffix.endsWith("/identity")) ? [
    { name: "source_account_ref", type: "string", required: true, description: "来源账号，后端验证数据范围" },
    { name: "idempotency_key", type: "UUID", required: true, description: "同请求重试保持，变更请求不可复用" },
    { name: suffix === "/drafts" ? "selections" : "expected_version", type: suffix === "/drafts" ? "array" : "integer", required: true, description: "来源订单/装箱行及版本；完整契约见 docs/api/pmc-wfs-pending-packing-api.md" },
  ] : [],
  returnFields: [{ name: "data", type: "object", required: true, description: "列表items/total、统计、选项、详情或pending草稿；不返回密钥" }],
  requestExample: { method, url: `/api/pmc/wfs/pending-packing${suffix}` },
  responseExample: { success: true, data: suffix === "/orders" ? { items: [], total: 0 } : {}, error: null, meta: { source: "new_system_postgresql", execution_enabled: false }, request_id: "example" },
}));
export const wfsPendingApiDocs: ApiDocModule = { key: "pmc-wfs", name: "PMC WFS", icon: "📦", desc: "待发货打包单真实接口", levels: [{ name: "待发货打包单", desc: "本系统装箱、分票与自动审批", apis }] };

const boardEndpoints: [ApiMethod, string, string][] = [
  ["GET", "/shipments", "货件看板列表"],
  ["GET", "/shipments/{row_id}", "货件详情"],
  ["GET", "/summary", "货件看板统计"],
  ["GET", "/filter-options", "货件看板店铺选项"],
];
const boardApis: ApiDocItem[] = boardEndpoints.map(([method, suffix, title]) => ({
  id: `pmc-wfs-board-${method}-${suffix}`,
  moduleKey: "pmc-wfs-board",
  moduleName: "PMC WFS 货件看板",
  levelName: "货件看板 M1",
  levelDesc: "本系统创建货件与标签；领星履约 M1 未接入",
  method,
  title,
  path: `/api/pmc/wfs/shipment-board${suffix}`,
  purpose: title,
  requestMode: "Query / 无 Body",
  successReturn: "{success,data,error,meta,request_id}",
  scenario: "WFS 货件看板只读",
  authScope: "page:pmc:wfs:view；来源账号及店铺数据范围",
  queryParams: [],
  bodyParams: [],
  returnFields: [{ name: "data", type: "object", required: true, description: "货件行、统计或店铺选项" }],
  requestExample: { method, url: `/api/pmc/wfs/shipment-board${suffix}` },
  responseExample: { success: true, data: suffix === "/shipments" ? { items: [], total: 0 } : {}, error: null, meta: { lingxing_sync_enabled: false }, request_id: "example" },
}));

export const wfsShipmentBoardApiDocs: ApiDocModule = {
  key: "pmc-wfs-board",
  name: "PMC WFS 货件看板",
  icon: "🚚",
  desc: "创建货件只读看板 M1",
  levels: [{ name: "货件看板", desc: "creation labels 投影", apis: boardApis }],
};

const exceptionEndpoints: [ApiMethod, string, string][] = [
  ["GET", "/cases", "异常案件列表"],
  ["GET", "/cases/{case_id}", "异常案件详情"],
  ["GET", "/summary", "异常中心统计"],
  ["GET", "/filter-options", "筛选选项"],
  ["POST", "/cases/{case_id}/assign", "分配负责人"],
  ["POST", "/cases/{case_id}/events", "处理事件"],
];
const exceptionApis: ApiDocItem[] = exceptionEndpoints.map(([method, suffix, title]) => ({
  id: `pmc-wfs-exception-${method}-${suffix}`,
  moduleKey: "pmc-wfs-exception",
  moduleName: "PMC WFS 异常中心",
  levelName: "异常中心 M1",
  levelDesc: "案件持久化与人工处理；自动规则 M1 STUB",
  method,
  title,
  path: `/api/pmc/wfs/exception-center${suffix}`,
  purpose: title,
  requestMode: method === "GET" ? "Query / 无 Body" : "JSON Body",
  successReturn: "{success,data,error,meta,request_id}",
  scenario: "WFS 异常中心",
  authScope: "page:pmc:wfs:view；assign/handle 动作权限；店铺数据范围",
  queryParams: [],
  bodyParams: [],
  returnFields: [{ name: "data", type: "object", required: true, description: "案件、统计或选项" }],
  requestExample: { method, url: `/api/pmc/wfs/exception-center${suffix}` },
  responseExample: { success: true, data: {}, error: null, meta: { rule_engine: "M1_STUB" }, request_id: "example" },
}));

export const wfsExceptionCenterApiDocs: ApiDocModule = {
  key: "pmc-wfs-exception",
  name: "PMC WFS 异常中心",
  icon: "⚠️",
  desc: "异常案件 M1",
  levels: [{ name: "异常中心", desc: "持久化案件与处理 API", apis: exceptionApis }],
};
