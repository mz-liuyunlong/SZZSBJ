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
export const domesticWarehouseApiDocs: ApiDocModule = {
  key: "pmc", name: "PMC", icon: "📦", desc: "国内仓真实只读契约；本地实现，部署待联合验收",
  levels: [{ name: "国内仓看板", desc: "店铺与当前产品负责人筛选", apis: [options, ...queries] }],
};
