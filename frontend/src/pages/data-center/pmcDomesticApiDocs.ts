/** Domestic filter contract entries use the real envelope; examples contain no business records. */
import type { ApiDocItem, ApiDocModule } from "./apiDocsTypes";

const common = {
  moduleKey: "pmc", moduleName: "PMC", levelName: "国内仓看板",
  levelDesc: "收货批次查询和当前产品负责人筛选", method: "GET" as const,
  requestMode: "Query / 无 Body", scenario: "国内仓批次看板",
  authScope: "pmc:domestic-batch:read；现有页面权限策略及可信 source-account scope",
  bodyParams: [],
};
const ownerParam = { name: "owner_uid", type: "string[]", required: false,
  description: "重复参数，最多50项，当前产品负责人UID；与其他条件AND，同字段OR" };
const options: ApiDocItem = {
  ...common, id: "pmc-domestic-filter-options", title: "国内仓店铺与负责人选项",
  path: "/api/pmc/domestic/filter-options", purpose: "返回可见批次的店铺ID/名称和当前产品负责人UID/名称；未知身份不猜归属。",
  successReturn: "{ success, data: { stores, owners }, error, meta, request_id }",
  queryParams: [], returnFields: [
    { name: "stores[]", type: "{value:string,label:string}", required: true, description: "value为真实店铺ID，名称歧义时label展示ID" },
    { name: "owners[]", type: "{value:string,label:string}", required: true, description: "value为当前产品负责人UID，同名不同UID分开保留" },
  ],
  requestExample: { method: "GET", url: "/api/pmc/domestic/filter-options" },
  responseExample: { success: true, data: { stores: [], owners: [] }, error: null,
    meta: { source: "new_system_postgresql", freshness_at: null }, request_id: "example-request" },
};
const queries: ApiDocItem[] = ["batches", "batches/summary"].map((path) => ({
  ...common, id: `pmc-domestic-${path.replace("/", "-")}`, title: path.endsWith("summary") ? "国内仓批次统计" : "国内仓批次列表",
  path: `/api/pmc/domestic/${path}`, purpose: "列表和统计使用相同店铺、当前负责人、日期、SKU条件；不会改变到仓日期口径。",
  successReturn: "统一 success/data/error/meta/request_id；完整字段见 docs/api/pmc-domestic-batch-board-api.md",
  queryParams: [ownerParam, { name: "store_id", type: "string[]", required: false, description: "真实店铺ID，最多50项；完整既有筛选见Markdown API文档" }],
  returnFields: [{ name: "data", type: "object", required: true, description: "列表items/total或收货行统计；按账号范围过滤" }],
  requestExample: { method: "GET", url: `/api/pmc/domestic/${path}`, query: { owner_uid: ["<uid>"] } },
  responseExample: { success: true, data: path.endsWith("summary")
    ? { receipt_batch_count: 0, received_qty: 0, warehouse_count: 0, matched_batch_count: 0,
      unresolved_batch_count: 0, missing_arrival_date_count: 0, as_of: "2026-10-19" }
    : { items: [], total: 0 }, error: null, meta: { source: "new_system_postgresql" }, request_id: "example-request" },
}));
const inboundQueries: ApiDocItem[] = [
  ["", "入库单批次列表"], ["/summary", "入库单及余额去重统计"],
  ["/filter-options", "入库批次店铺与当前负责人选项"],
  ["/{id}", "入库单批次详情"], ["/{id}/trace", "入库事件来源追溯"],
].map(([suffix, title]) => ({
  ...common, id: `pmc-domestic-inbound-${suffix || "list"}`, title,
  path: `/api/pmc/domestic/inbound-batches${suffix}`,
  purpose: "独立IB×SKU×店铺批次口径；原收货接口不变；余额0不代表已发货。",
  successReturn: "统一success/data/error/meta/request_id；详见pmc-domestic-inbound-board-api.md",
  queryParams: suffix.includes("{id}") ? [] : [{ name: "warehouse_id", type: "string[]", required: false,
    description: suffix === "/filter-options" ? "完整可见入库批次范围的仓库筛选；仅接受warehouse_id" : "仓库筛选；另支持store_id、sku、入库单、采购单、入库日期、库存已知状态及当前产品负责人owner_uid（最多50项，重复参数）" }],
  returnFields: [{ name: "meta.data_status", type: "not_published | ready", required: true,
    description: "区分尚未发布与筛选后无记录；GET不调用领星，不自动读取CSV。" }],
  requestExample: { method: "GET", url: `/api/pmc/domestic/inbound-batches${suffix}` },
  responseExample: suffix.includes("{id}")
    ? { success: false, data: null, error: { code: "NOT_FOUND", message: "资源不存在", details: {} },
        meta: null, request_id: "example-request" }
    : { success: true, data: suffix === "/summary"
        ? { board_row_count: 0, inbound_order_count: 0, sku_count: 0, balance_qty: 0,
            unknown_inventory_row_count: 0, total_inbound_qty: 0, unknown_inbound_qty_count: 0,
            missing_arrival_date_count: 0, as_of: "2026-10-20" }
        : suffix === "/filter-options" ? { stores: [], owners: [], statuses: [], owner_basis: "current_product_owner" } : { items: [], total: 0 }, error: null,
        meta: { source: "new_system_postgresql", data_status: "not_published", publication_ids: [],
          freshness_at: null, as_of: "2026-10-20" }, request_id: "example-request" },
}));

const packingQueries: ApiDocItem[] = [
  ["/pending", "待审批列表"], ["/pending/summary", "审批汇总"], ["/filter-options", "审批选项"],
  ["/orders", "审批记录"], ["/orders/{id}", "审批详情"], ["/orders/{id}/events", "审批审计"],
].map(([suffix, title]) => ({
  ...common, id: `pmc-packing-${suffix}`, title, path: `/api/pmc/domestic/packing-approval${suffix}`,
  scenario: "国内仓打包单审批", purpose: "仅本地M1；当前发布入库及OPS审批，完整契约见pmc-domestic-packing-approval-api.md",
  successReturn: "统一success/data/error/meta/request_id", queryParams: [],
  returnFields: [{ name: "data", type: "object", required: true, description: "列表items/total、汇总、选项或审批快照；详见Markdown契约" }],
  requestExample: { method: "GET", url: `/api/pmc/domestic/packing-approval${suffix}` },
  responseExample: { success: true, data: { items: [], total: 0 }, error: null, meta: { source: "new_system_postgresql" }, request_id: "example" },
}));
const packingWrites: ApiDocItem[] = ["approve", "reject"].map((kind) => ({
  ...common, method: "POST" as const, id: `pmc-packing-${kind}`, title: kind === "approve" ? "通过打包审批" : "驳回打包审批",
  path: `/api/pmc/domestic/packing-approval/pending/{id}/${kind}`, requestMode: "JSON Body", scenario: "本地打包审批",
  authScope: `action:pmc:domestic-warehouse-board:packing-${kind} + 来源账号范围`, purpose: "原子审批及幂等审计，仅写本地验证单，不创建OWS",
  successReturn: "统一envelope，data为订单详情及来源snapshot", queryParams: [],
  bodyParams: [{ name: "source_account_ref / candidate_version / idempotency_key", type: "string", required: true, description: "可信来源、版本和幂等UUID；approve另需qty，reject另需note，完整约束见Markdown契约" }],
  returnFields: [{ name: "data", type: "object", required: true, description: "id、pk、status、qty、version、is_test、snapshot；驳回pk为null" }],
  requestExample: { method: "POST", url: `/api/pmc/domestic/packing-approval/pending/{id}/${kind}` },
  responseExample: { success: false, data: null, error: { code: "INVALID_REQUEST", message: "请求无效", details: { reason: "SOURCE_CHANGED" } }, meta: null, request_id: "example" },
}));

export const domesticWarehouseApiDocs: ApiDocModule = {
  key: "pmc", name: "PMC", icon: "📦", desc: "国内仓真实只读契约；本地实现，部署待联合验收",
  levels: [{ name: "国内仓看板", desc: "店铺与当前产品负责人筛选", apis: [options, ...queries, ...inboundQueries, ...packingQueries, ...packingWrites] }],
};
