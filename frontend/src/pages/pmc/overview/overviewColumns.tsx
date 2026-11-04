/**
 * ItemID main-table column definitions (one place, stable keys). Shared by `OverviewTable` and
 * the runtime column drawer; widths / visible keys are a per-browser preference only.
 */
import type { ProColumns } from "@ant-design/pro-components";
import { Space, Tag, Tooltip, Typography } from "antd";
import type { ReactNode } from "react";
import type { RuntimeColumnField, RuntimeColumnGroup } from "@/components/report-table/RuntimeColumnConfigDrawer";
import { StatusTagCell, WalmartItemLink } from "@/components/report-table/cells";
import { CAT_COLOR, coverFallback, domAvailable, fmt, fmt1, poOutstanding } from "@/pages/pmc/overview/overviewDisplay";
import type { OverviewItemRow, OverviewSortKey } from "@/pages/pmc/overview/overviewTypes";

export const EMPTY = <Typography.Text type="secondary">—</Typography.Text>;
const muted = (children: ReactNode) => <Typography.Text type="secondary">{children}</Typography.Text>;

interface FieldDef extends RuntimeColumnField {
  width: number;
  minWidth: number;
  align?: "right";
  /** Server-side sort key (whitelist in `OVERVIEW_SORTS`). */
  sortBy?: OverviewSortKey;
}

export const overviewColumnFields: FieldDef[] = [
  { key: "item_id", title: "ItemID", width: 124, minWidth: 110 },
  { key: "sku", title: "SKU / 品名", width: 200, minWidth: 150 },
  { key: "msku", title: "MSKU", width: 130, minWidth: 100 },
  { key: "stores", title: "店铺", width: 150, minWidth: 110 },
  { key: "owner", title: "负责人", width: 86, minWidth: 72 },
  { key: "main", title: "主要问题", width: 240, minWidth: 160 },
  { key: "po", title: "采购未到", width: 90, minWidth: 80, align: "right" },
  { key: "dom", title: "国内仓 可用/锁定", width: 124, minWidth: 110, align: "right" },
  { key: "shipped", title: "已发货未可售", width: 110, minWidth: 96, align: "right" },
  { key: "receiving", title: "已到·收货中", width: 104, minWidth: 90, align: "right" },
  { key: "wfs", title: "WFS 可售", width: 100, minWidth: 86, align: "right", sortBy: "wm_available" },
  { key: "supply", title: "全链路供应", width: 110, minWidth: 96, align: "right", sortBy: "supply" },
  { key: "daily", title: "日销", width: 84, minWidth: 72, align: "right", sortBy: "daily" },
  { key: "n30", title: "有库存天数", width: 106, minWidth: 96, align: "right", sortBy: "n30" },
  { key: "oos_days", title: "断货天数", width: 100, minWidth: 86, align: "right", sortBy: "oos_days" },
  { key: "sellout", title: "能卖到", width: 108, minWidth: 96 },
  { key: "next", title: "下一批可售", width: 108, minWidth: 96 },
  { key: "gap", title: "预计断货天数", width: 120, minWidth: 106, align: "right", sortBy: "gap_days" },
  { key: "cover", title: "覆盖天数", width: 100, minWidth: 86, align: "right", sortBy: "cover" },
  { key: "draft", title: "补货状态", width: 210, minWidth: 140 },
  { key: "issues", title: "全部提示", width: 260, minWidth: 160 },
];

export const fixedOverviewColumnKeys = ["item_id", "sku"];
export const overviewDefaultColumnKeys = overviewColumnFields.map((f) => f.key);
export const overviewDefaultColumnWidths = Object.fromEntries(overviewColumnFields.map((f) => [f.key, f.width]));
export const overviewColumnGroups: RuntimeColumnGroup[] = [
  { title: "商品", fields: overviewColumnFields.slice(0, 6) },
  { title: "库存分段", fields: overviewColumnFields.slice(6, 12) },
  { title: "销售与断货", fields: overviewColumnFields.slice(12) },
];
const fieldOf = Object.fromEntries(overviewColumnFields.map((f) => [f.key, f]));
export const sortKeyOf = (columnKey: string): OverviewSortKey | undefined => fieldOf[columnKey]?.sortBy;
export const minWidthOf = (columnKey: string) => fieldOf[columnKey]?.minWidth ?? 96;

type Render = (row: OverviewItemRow) => ReactNode;

/** Cell renderers by column key; values are shown as delivered by `/api/pmc/overview/items`. */
export function overviewCellRenderers(salesMinDays: number): Record<string, Render> {
  return {
    item_id: (r) => <WalmartItemLink itemId={r.item_id} />,
    sku: (r) => <span className="pmc-overview__sku-cell"><b>{r.sku}</b>{muted(r.name)}</span>,
    msku: (r) => (r.msku ? <span className="pmc-overview__mono">{r.msku}</span> : EMPTY),
    stores: (r) => (r.stores.length ? (
      <Tooltip title={r.stores.map((s) => `${s.name}：销 ${s.sales30} · 可售 ${s.available} · 在途 ${s.intransit}`).join("\n")}>
        <span>{r.stores[0].name.split("-")[0]}{r.stores.length > 1 && <Tag bordered={false} className="pmc-overview__store-more">+{r.stores.length - 1} 店</Tag>}</span>
      </Tooltip>
    ) : EMPTY),
    owner: (r) => r.owner || EMPTY,
    main: (r) => (r.issues.length
      ? <span className="pmc-overview__main-cell"><StatusTagCell label={r.main} color={CAT_COLOR[r.main] ?? r.level} />{muted(r.issues[0].detail)}</span>
      : <StatusTagCell label="正常" color="success" />),
    po: (r) => fmt(poOutstanding(r)),
    dom: (r) => `${fmt(domAvailable(r))} / ${fmt(r.dom_lock)}`,
    shipped: (r) => fmt(r.seg.shipped ?? 0),
    receiving: (r) => fmt(r.seg.receiving ?? 0),
    wfs: (r) => <span className={r.oos ? "pmc-overview__neg" : undefined}>{fmt(r.wm_available)}</span>,
    supply: (r) => <b>{fmt(r.supply)}</b>,
    daily: (r) => fmt1(r.daily),
    n30: (r) => <span className={r.n30 < 30 ? "pmc-overview__warn" : undefined}>{r.n30}</span>,
    oos_days: (r) => (r.oos_days === null ? muted("90+") : r.oos_days > 0 ? <b className="pmc-overview__neg">{r.oos_days}</b> : muted("0")),
    sellout: (r) => (r.sellout ? <span className={r.risk || r.oos ? "pmc-overview__neg" : undefined}>{r.sellout}</span> : muted(r.daily > 0 ? "400 天+" : "—")),
    next: (r) => r.next_date || EMPTY,
    gap: (r) => (r.gap_days !== null ? <b className="pmc-overview__neg">{r.gap_days}</b> : muted(r.sellout ? "无来货" : "—")),
    cover: (r) => (r.cover !== null ? <span className={r.over === "严重过剩" ? "pmc-overview__warn" : undefined}>{fmt(r.cover)}</span> : muted(coverFallback(r, salesMinDays))),
    draft: (r) => (r.is_draft ? r.draft_text : muted(r.draft_text)),
    issues: (r) => (r.issues.length > 1
      ? <Space size={[4, 4]} wrap>{r.issues.slice(1).map((i) => <StatusTagCell key={i.label} label={i.label} color={i.level} />)}</Space>
      : EMPTY),
  };
}

export type OverviewColumn = ProColumns<OverviewItemRow>;
export const fieldMeta = (key: string) => fieldOf[key];
