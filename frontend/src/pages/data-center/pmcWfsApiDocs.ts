/** Actual WFS preparation endpoints; examples are empty and never invoke external systems. */
import type { ApiDocItem, ApiDocModule, ApiMethod } from "./apiDocsTypes";
const endpoints: [ApiMethod, string, string][] = [
  ["GET", "/orders", "待发货打包单列表"], ["GET", "/summary", "待发货打包单统计"],
  ["GET", "/filter-options", "待发货真实店铺选项"], ["GET", "/orders/{id}", "待发货单据详情"],
  ["GET", "/orders/{id}/identity-options", "同 SKU 目标商品身份"],
  ["POST", "/orders/{id}/identity", "换店铺或链接并生成新 PK"],
  ["POST", "/drafts", "生成待审批货件草稿"], ["GET", "/drafts/{id}", "读取草稿回执"],
];
const apis: ApiDocItem[] = endpoints.map(([method, suffix, title]) => ({
  id: `pmc-wfs-pending-${method}-${suffix}`, moduleKey: "pmc-wfs", moduleName: "PMC WFS",
  levelName: "待发货打包单", levelDesc: "本系统装箱、草稿与占用；无 Walmart 执行", method, title,
  path: `/api/pmc/wfs/pending-packing${suffix}`, purpose: title,
  requestMode: method === "GET" ? "Query / 无 Body" : "JSON Body",
  successReturn: "{success,data,error,meta,request_id}", scenario: "待发货打包单页面真实接口",
  authScope: "page:pmc:wfs:view；独立动作 permissionKey；来源账号及店铺数据范围",
  queryParams: suffix === "/orders" || suffix === "/summary" ? [
    { name: "store_id", type: "string", required: false, description: "目标店铺ID" },
    { name: "keyword", type: "string", required: false, description: "PK、SKU、ItemID、GTIN、MSKU" },
    { name: "only_test", type: "boolean", required: false, description: "仅业务测试记录" },
  ] : [],
  bodyParams: method === "POST" ? [
    { name: "source_account_ref", type: "string", required: true, description: "来源账号，后端验证数据范围" },
    { name: "idempotency_key", type: "UUID", required: true, description: "同请求重试保持，变更请求不可复用" },
    { name: suffix === "/drafts" ? "selections" : "expected_version", type: suffix === "/drafts" ? "array" : "integer", required: true, description: "来源订单/装箱行及版本；完整契约见 docs/api/pmc-wfs-pending-packing-api.md" },
  ] : [],
  returnFields: [{ name: "data", type: "object", required: true, description: "列表items/total、统计、选项、详情或pending草稿；不返回密钥" }],
  requestExample: { method, url: `/api/pmc/wfs/pending-packing${suffix}` },
  responseExample: { success: true, data: suffix === "/orders" ? { items: [], total: 0 } : {}, error: null, meta: { source: "new_system_postgresql", execution_enabled: false }, request_id: "example" },
}));
export const wfsPendingApiDocs: ApiDocModule = { key: "pmc-wfs", name: "PMC WFS", icon: "📦", desc: "待发货打包单真实接口", levels: [{ name: "待发货打包单", desc: "真实本地数据与待审批草稿", apis }] };
