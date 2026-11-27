// Only named business evidence is rendered; no provider payloads or guessed identities.
export const sampleAnomalyNames: Record<string, string> = {
  DATA_PAGES_VERIFIED_SAMPLE_CHANGED: "已确认送样证据变化",
  DATA_PAGES_VERIFIED_SAMPLE_NOT_OBSERVED: "已确认送样订单未返回",
  DATA_PAGES_VERIFIED_LINE_ALIAS_AMBIGUOUS: "送样订单行身份冲突",
  DATA_PAGES_SAMPLE_CANCELLATION_APPLIED: "送样订单已取消",
};

export const sampleAnomalyGuide: Record<string, string> = {
  DATA_PAGES_VERIFIED_SAMPLE_CHANGED:
    "按下方订单号、店铺及变化字段在领星核对原值与新值。补齐或修正来源证据后，回任务中心按美国业务日期补同步；仅保存备注不会解除隔离。",
  DATA_PAGES_VERIFIED_SAMPLE_NOT_OBSERVED:
    "在领星核对该日订单及订单行是否完整返回。缺失不等于取消，补齐来源后按美国业务日期补同步。",
  DATA_PAGES_VERIFIED_LINE_ALIAS_AMBIGUOUS:
    "核对平台订单号、来源订单号和订单行号，确认唯一身份后补同步，不要猜测商品归属。",
  DATA_PAGES_SAMPLE_CANCELLATION_APPLIED:
    "系统根据明确取消证据自动撤销送样资格，保留历史记录。财务已复验时无需人工处理；待复验时按美国业务日期补同步。",
};

const fieldNames: Record<string, string> = {
  business_date_utc_minus_7: "美国业务日期",
  source_order_id: "来源订单号",
  platform_order_no: "平台订单号",
  store_id: "店铺 ID",
  platform_code: "平台",
  source_order_line_id: "订单行号",
  item_id: "Item ID",
  msku: "MSKU",
  local_sku: "SKU",
  quantity: "件数",
  unit_price_amount: "单价",
  unit_price_currency_code: "单价币种",
  order_total_amount: "订单金额",
  order_total_currency_code: "订单币种",
  cancel_time_raw: "取消时间（来源原值）",
  is_cancelled: "是否取消",
};

export const evidenceValue = (value: unknown): string => {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value.trim() || "未提供";
  return "未提供";
};

export interface EvidenceChange {
  field: string;
  previous: string;
  observed: string;
}

export function evidenceChanges(details: Record<string, unknown>): EvidenceChange[] {
  if (!Array.isArray(details.changes)) return [];
  return details.changes.flatMap((row: unknown) => {
    if (!row || typeof row !== "object" || !("field" in row) ||
        typeof row.field !== "string" || !Object.hasOwn(fieldNames, row.field)) return [];
    return [{
      field: fieldNames[row.field],
      previous: evidenceValue("previous" in row ? row.previous : undefined),
      observed: evidenceValue("observed" in row ? row.observed : undefined),
    }];
  });
}

export function sampleReviewBlocked(details: Record<string, unknown>): boolean {
  return details.sample_isolation_active === true ||
    ("sample_isolation_active" in details && details.financial_status === "pending");
}

export function sampleFinancialStatus(details: Record<string, unknown>): string {
  if (details.sample_isolation_active === true || details.financial_status === "partial") {
    return "争议商品利润待核实";
  }
  if (details.financial_status === "ready") return "已复验";
  return "待复验";
}
