/** Local Vite-only Listing rule UI acceptance. NEVER used by the production app. */
import { Alert, Button, Card, Space, Typography } from "antd";
import { useState } from "react";
import type {
  ListingGradeRuleConfig,
  ListingGradeRuleHistory,
  ListingGradeRuleRead,
} from "@/pages/products/listingRuleConfigApi";
import ListingRuleConfigDrawer, {
  type ListingRuleTransport,
} from "@/pages/products/components/ListingRuleConfigDrawer";

const DEFAULT_CONFIG: ListingGradeRuleConfig = {
  execution_time: "22:30",
  short_days: 7,
  medium_days: 14,
  short_weight_percent: 60,
  medium_weight_percent: 40,
  short_min_valid_days: 4,
  medium_min_valid_days: 8,
  c_min_percent: "5",
  b_min_percent: "10",
  a_above_percent: "15",
  included_stages: ["打品期", "启动期", "上升期", "稳定期", "下滑期", "修复期"],
  lifecycle: {
    min_week_valid_days: 4,
    growth_min_valid_days_30: 14,
    stable_min_valid_days_30: 21,
    decline_min_valid_days_30: 21,
    growth_threshold_pct: { lt2: 50, from2to5: 40, from5to10: 30, from10to20: 25, gte20: 20 },
    decline_threshold_pct: { lt2: 50, from2to5: 40, from5to10: 30, from10to20: 25, gte20: 20 },
    stable_tolerance_pct: { lt2: 60, from2to5: 45, from5to10: 35, from10to20: 30, gte20: 25 },
  },
  inventory_repair: {
    low_stock_max_units: 5,
    stockout_consecutive_days: 7,
    long_stockout_days: 25,
    stockout_repair_valid_days: 15,
    strike_price_abnormal_days: 25,
    buybox_abnormal_days: 25,
    abnormal_recovery_days: 7,
  },
  follow_up: {
    reminder_time: null,
    deadline_time: null,
    overdue_notice: false,
  },
};

const PROTECTED = {
  execution_timezone: "Asia/Shanghai",
  business_timezone: "America/Los_Angeles",
  closing_lag_days: 2,
  requires_complete_financial_inputs: true,
  permanently_excluded_stages: ["清货期", "已归档"],
} as const;

const initialRule = (): ListingGradeRuleRead => ({
  version: 0,
  config: structuredClone(DEFAULT_CONFIG),
  protected: { ...PROTECTED, permanently_excluded_stages: [...PROTECTED.permanently_excluded_stages] },
  effective_from: null,
  created_at: null,
  created_by: null,
  change_reason: null,
  is_pending: false,
  source: "default",
  can_edit: true,
  storage_ready: true,
  preview_enabled: true,
  scheduler_enabled: false,
  publish_enabled: false,
});

let stored = initialRule();
let entries: ListingGradeRuleHistory["items"] = [];

const PREVIEW_TRANSPORT: ListingRuleTransport = {
  fetchRule: async () => structuredClone(stored),
  fetchHistory: async (limit = 20) => ({
    items: structuredClone(entries.slice(0, limit)),
    total: entries.length,
    storage_ready: true,
  }),
  saveRule: async (config, expectedVersion, reason) => {
    if (expectedVersion !== stored.version) throw new Error("Preview version conflict");
    if (reason.trim().length < 3) throw new Error("Preview reason required");
    const now = new Date().toISOString();
    const effectiveFrom = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    stored = {
      ...stored,
      version: stored.version + 1,
      source: "database",
      config: structuredClone(config),
      effective_from: effectiveFrom,
      created_at: now,
      created_by: "本地模拟用户",
      change_reason: reason,
      is_pending: true,
    };
    entries = [{
      version: stored.version,
      config: structuredClone(config),
      effective_from: effectiveFrom,
      created_at: now,
      created_by: "本地模拟用户",
      change_reason: reason,
    }, ...entries];
    return structuredClone(stored);
  },
};

export default function ListingRuleConfigPreview() {
  const [open, setOpen] = useState(true);

  return (
    <div style={{ padding: 32, maxWidth: 1000, margin: "0 auto" }}>
      <Space direction="vertical" size={24} style={{ width: "100%" }}>
        <Alert
          type="warning"
          showIcon
          message="Listing 规则配置 · 本地前端预览（模拟数据）"
          description="仅用于核对四组规则的布局、字段、输入、校验、模拟保存和版本记录。不会请求后端，不会写入生产或开发数据库。刷新页面后模拟版本会重置；模拟生效时间不代表实际调度。"
        />
        <Card>
          <Typography.Title level={4}>Listing 管理 / 规则配置</Typography.Title>
          <Typography.Paragraph type="secondary">
            这里直接复用 Listing 管理页面的正式规则配置 Drawer，支持打开、关闭与重新编辑。
          </Typography.Paragraph>
          <Button type="primary" onClick={() => setOpen(true)}>打开规则配置</Button>
        </Card>
      </Space>
      <ListingRuleConfigDrawer
        open={open}
        onClose={() => setOpen(false)}
        transport={PREVIEW_TRANSPORT}
      />
    </div>
  );
}
