import {buildDemoDailySales90} from "./purchaseApprovalDemoMetrics";
/** V3 demo-only business-specific columns and evidence. Never used for WFS cases. */
import { Button, Tag, Typography } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import type { ReactNode } from "react";
import type { ApprovalItem } from "./approvalTypes";
import { getDemoSeed } from "./approvalDemoData";
import type { ApprovalBusinessKey } from "./approvalBusiness";

export interface ClearanceSku {
  sku: string; msku: string; item: string; name: string;
  available: number; age: number; listingDays?: number; target: number; cost: number;
  price: number; rating: number; returnRate: number;
  sales: [number, number, number];
  revenue: [number, number, number];
  ad: [number, number, number];
  profit: [number, number, number];
}

export interface PurchaseApprovalAnalysisDemo {
  /** Explicit local sample values; this is never a fallback for production API. */
  dimensions?: {market:number;speed:number;ad:number;profit:number;trust:number};
  sellingPrice?: number; unitPurchaseCost?: number; unitOtherCost?: number;
  unitGrossProfit?: number; grossMarginPct?: number; roi?: number;
  adState?: "active" | "organic" | "none";
  acosPct?: number; cpc?: number; cvrPct?: number;
  adSpend?: number; adSales?: number; adClicks?: number; adOrders?: number;
  firstOrderDays?: number; validOrders14?: number;
  stockAvailable?: number; stockInbound?: number;
  profit30?: number; profitMargin30Pct?: number;
  adSpend30?: number; adSales30?: number; acos30Pct?: number;
  businessNote?: string;
  dailySales90?: number[];
}

export interface DemoBusinessProfile {
  kind: "purchase" | "clearance" | "listing" | "price";
  sku?: string; msku?: string; item?: string; product?: string;
  supplier?: string; quantity?: number; delivery?: string; owner?: string;
  methods?: string[]; targetQty?: number; deadline?: string; source?: string;
  clearanceSkus?: ClearanceSku[];
  listingStatus?: string; archiveWay?: string; stockAvailable?: number;
  openOrders?: number; archiveReason?: string;
  oldPrice?: number; newPrice?: number; minPrice?: number;
  oldMargin?: number; newMargin?: number; monthlySales?: number;
  linkedClearance?: string;
  purchaseAnalysis?: PurchaseApprovalAnalysisDemo;
  // 仅供现有 DEMO-* 采购记录预览；真实申请数据从 purchase_details 读取。
  purchaseKind?: "initial" | "replenishment";
  applicationSource?: "system" | "operator";
  suggestedQty?: number;
  scoreTotal?: number;
  initialGrade?: "S" | "A" | "B" | "C" | "D" | "Pass";
  estimatedSellableDays?: number;
  sales30Qty?: number;
}

const sku = (
  code: string, name: string, available: number, age: number, target: number,
  base: number, cost: number, rating: number, returnRate: number,
): ClearanceSku => ({
  sku: code, msku: `DEMO-MSKU-${code.split("-").at(-1)}`, item: `DEMO-ITEM-${code.split("-").at(-1)}`,
  name, available, age, target, cost, price: 15.99, rating, returnRate,
  sales: [Math.round(base * 0.28), Math.round(base * 0.53), base],
  revenue: [Math.round(base * 0.28 * 15.99), Math.round(base * 0.53 * 15.99), Math.round(base * 15.99)],
  ad: [Math.round(base * .4), Math.round(base * .7), Math.round(base * 1.3)],
  profit: [Math.round(base * .25) - 32, Math.round(base * .5) - 65, Math.round(base * .9) - 120],
});

/** Exact IDs are deliberately limited to the existing twelve demo-only records. */
export const demoProfiles: Readonly<Record<string, DemoBusinessProfile>> = {
  "DEMO-PO-001": { kind: "purchase", supplier: "演示·深圳包装供应商", quantity: 240, delivery: "2026-11-10", owner: "演示运营A", sku: "DEMO-SKU-101", product: "厨房收纳盒套装", purchaseKind: "initial", applicationSource: "system", suggestedQty: 300, scoreTotal: 8.65, initialGrade: "A", purchaseAnalysis: { dimensions: {market:8.3,speed:9.1,ad:8.5,profit:8.9,trust:7.5}, sellingPrice:20.99, unitPurchaseCost:11.92, unitOtherCost:3.97, unitGrossProfit:5.10, grossMarginPct:24.3, roi:1.42, adState:"active", acosPct:23.8, cpc:0.33, cvrPct:6.5, adSpend:14.99, adSales:62.97, adClicks:46, adOrders:3, firstOrderDays:3, validOrders14:22 } },
  "DEMO-PO-002": { kind: "purchase", supplier: "演示·东莞五金供应商", quantity: 600, delivery: "2026-11-05", owner: "演示运营B", sku: "DEMO-SKU-102", product: "厨房不锈钢压泥器", purchaseKind: "replenishment", applicationSource: "operator", suggestedQty: 500, estimatedSellableDays: 12, sales30Qty: 180, purchaseAnalysis: { dailySales90:buildDemoDailySales90(180,2), stockAvailable:72, stockInbound:80, profit30:680, profitMargin30Pct:18.5, adSpend30:66.60, adSales30:310, acos30Pct:21.5, businessNote:"销量稳定，提前补足安全库存" } },
  "DEMO-PO-003": { kind: "purchase", supplier: "演示·深圳塑胶供应商", quantity: 180, delivery: "2026-11-18", owner: "演示运营C", sku: "DEMO-SKU-103", product: "抽屉分格收纳盒", purchaseKind: "replenishment", applicationSource: "system", suggestedQty: 200, estimatedSellableDays: 5, sales30Qty: 320, purchaseAnalysis: { dailySales90:buildDemoDailySales90(320,3), stockAvailable:53, stockInbound:0, profit30:390, profitMargin30Pct:11.2, adSpend30:94.80, adSales30:480, acos30Pct:19.8, businessNote:"库存覆盖偏低，需关注到货时效" } },
  "DEMO-CLR-001": { kind: "clearance", targetQty: 120, deadline: "2026-11-25", source: "运营主动申请", methods: ["折扣促销", "WFS移除"], clearanceSkus: [sku("DEMO-SKU-201", "厨房密封储物罐", 450, 220, 70, 35, 8.6, 4.2, 5.4), sku("DEMO-SKU-204", "抽屉收纳分隔盒", 310, 193, 50, 23, 7.4, 4.0, 4.1)] },
  "DEMO-CLR-002": { kind: "clearance", targetQty: 80, deadline: "2026-11-20", source: "系统风险识别", methods: ["降价", "捆绑促销"], clearanceSkus: [sku("DEMO-SKU-202", "厨房可堆叠收纳盒", 280, 168, 80, 62, 6.7, 4.4, 3.2)] },
  "DEMO-CLR-003": { kind: "clearance", targetQty: 140, deadline: "2026-12-08", source: "运营主动申请", methods: ["折扣促销"], clearanceSkus: [sku("DEMO-SKU-203", "冰箱收纳篮", 140, 81, 140, 130, 6.1, 4.5, 2.6)] },
  "DEMO-LST-001": { kind: "listing", item: "DEMO-ITEM-301", sku: "DEMO-SKU-301", msku: "DEMO-MSKU-301", product: "老款收纳盒", listingStatus: "已停用", archiveWay: "停用后归档", stockAvailable: 0, openOrders: 0 },
  "DEMO-LST-002": { kind: "listing", item: "DEMO-ITEM-302", sku: "DEMO-SKU-302", msku: "DEMO-MSKU-302", product: "重复刊登的储物盒", listingStatus: "已下架", archiveWay: "冗余 Listing 归档", stockAvailable: 0, openOrders: 0 },
  "DEMO-LST-003": { kind: "listing", item: "DEMO-ITEM-303", sku: "DEMO-SKU-303", msku: "DEMO-MSKU-303", product: "旧版厨房分格盒", listingStatus: "在售", archiveWay: "升级换代归档", stockAvailable: 126, openOrders: 9 },
  "DEMO-PRC-001": { kind: "price", sku: "DEMO-SKU-401", msku: "DEMO-MSKU-401", item: "DEMO-ITEM-401", product: "厨房沥水架", oldPrice: 19.99, newPrice: 17.99, minPrice: 16.99, oldMargin: 16.7, newMargin: 9.1, monthlySales: 180, linkedClearance: "无" },
  "DEMO-PRC-002": { kind: "price", sku: "DEMO-SKU-402", msku: "DEMO-MSKU-402", item: "DEMO-ITEM-402", product: "密封零食盒", oldPrice: 14.99, newPrice: 15.99, minPrice: 13.99, oldMargin: 15.0, newMargin: 19.2, monthlySales: 220, linkedClearance: "无" },
  "DEMO-PRC-003": { kind: "price", sku: "DEMO-SKU-403", msku: "DEMO-MSKU-403", item: "DEMO-ITEM-403", product: "厨房调味瓶", oldPrice: 12.99, newPrice: 9.49, minPrice: 10.49, oldMargin: 12.5, newMargin: -4.8, monthlySales: 125, linkedClearance: "无" },
};

export function primaryClearanceSku(row: Pick<ApprovalItem, "id">): ClearanceSku | undefined {
  const seed = getDemoSeed(row.id);
  return demoProfiles[row.id]?.clearanceSkus?.find((item) => item.sku === seed?.sku);
}

const money = (value: number | string | null | undefined) => value == null ? "—" : `$${Number(value).toFixed(2)}`;
const quantity = (value: number | undefined) => value == null ? "—" : `${value.toLocaleString("zh-CN")} 件`;
const percent = (n: number | undefined) => n == null ? "—" : `${n.toFixed(1)}%`;
const delta = (p: DemoBusinessProfile) => p.oldPrice && p.newPrice != null ? (p.newPrice - p.oldPrice) / p.oldPrice * 100 : null;
const titleByStatus: Record<string, string> = { submitted: "待审批", approved: "已审批", rejected: "驳回记录" };
const riskNames: Record<string, string> = { low: "低风险", medium: "中风险", high: "高风险", unknown: "待评估" };

function col(key: string, title: string, width: number, cell: (r: ApprovalItem) => ReactNode): ProColumns<ApprovalItem> {
  return { key, title, width, render: (_value, row) => cell(row) };
}

/** Independent columns mirror SPEC in the uploaded V3 HTML demo. */
export function demoColumnsForBusiness(
  business: ApprovalBusinessKey,
  onDetail: (item: ApprovalItem) => void,
  onAction?: (item: ApprovalItem, action: "approve" | "reject") => void,
): ProColumns<ApprovalItem>[] | null {
  if (!["purchase", "clearance", "listing", "price"].includes(business)) return null;
  const profile = (row: ApprovalItem) => demoProfiles[row.id];
  const common = {
    title: col("title", business === "purchase" ? "采购事项" : business === "clearance" ? "申请单 / 商品" : business === "listing" ? "归档申请 / 商品" : "调价申请 / 商品", 235, r => <div className="approval-demo__subject"><Button type="link" size="small" onClick={() => onDetail(r)}>{r.title}</Button><small>{r.business_ref} · {r.source_account_ref}</small></div>),
    risk: col("risk", "风险", 90, r => <Tag color={r.risk_level === "high" ? "red" : r.risk_level === "medium" ? "orange" : "green"}>{riskNames[r.risk_level]}</Tag>),
    applicant: col("applicant", "申请人", 105, r => r.applicant_id),
    submitted: col("submitted", "提交时间", 144, r => r.submitted_at ? new Date(r.submitted_at).toLocaleString("zh-CN", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}) : "—"),
    status: col("status", "状态", 100, r => <Tag color={r.status === "approved" ? "success" : r.status === "rejected" ? "error" : "processing"}>{titleByStatus[r.status] || r.status}</Tag>),
    action: col("action", "操作", 108, r => <Button type="link" size="small" onClick={() => onDetail(r)}>查看详情</Button>),
  };
  // PR337_PURCHASE_APPROVAL_TABLE_V1: unified first-purchase/replenishment display.
  if (business === "purchase") {
    // purchase_details is reserved for the real API. DEMO-* profiles are local-only.
    // Missing figures render as dashes; do not infer scoring or sales from other fields.
    const info = (row: ApprovalItem) => {
      const live = row.purchase_details;
      const mock = row.id.startsWith("DEMO-") ? profile(row) : undefined;
      return {
        kind: live?.purchase_kind ?? mock?.purchaseKind,
        source: live?.application_source ?? mock?.applicationSource,
        name: live?.product_name ?? mock?.product,
        sku: live?.sku ?? mock?.sku,
        store: live?.store_name ?? (mock ? row.source_account_ref : undefined),
        owner: live?.owner_name ?? mock?.owner,
        score: live?.score_total ?? mock?.scoreTotal,
        grade: live?.initial_grade ?? mock?.initialGrade,
        days: live?.estimated_sellable_days ?? mock?.estimatedSellableDays,
        sold30: live?.sales_30d ?? mock?.sales30Qty,
        suggested: live?.suggested_qty ?? mock?.suggestedQty,
        requested: live?.requested_qty ?? mock?.quantity,
        supplier: live?.supplier_name ?? mock?.supplier,
        delivery: live?.required_delivery_date ?? mock?.delivery,
        amount: live?.amount ?? row.amount,
        currency: live?.currency_code ?? row.currency_code,
      };
    };
    const stacked = (main: ReactNode, secondary: ReactNode) => (
      <div className="approval-demo__subject">
        <strong>{main}</strong>
        <small>{secondary}</small>
      </div>
    );
    const qty = (v: number | null | undefined) =>
      v === null || v === undefined ? "—" : `${v.toLocaleString("zh-CN")} 件`;
    const amountText = (row: ApprovalItem) => {
      const item = info(row);
      if (item.amount === undefined || item.amount === null || item.amount === "") return "—";
      const n = Number(item.amount);
      if (!Number.isFinite(n)) return "—";
      return `${item.currency ? item.currency + " " : ""}${n.toFixed(2)}`;
    };
    const kindText = (v: string | null | undefined) =>
      v === "initial" ? "新品首采" : v === "replenishment" ? "后续补货" : "类型待确认";
    const sourceText = (v: string | null | undefined) =>
      v === "system" ? "系统自动申请" : v === "operator" ? "运营主动申请" : "来源待确认";
    return [
      col("product", "商品信息", 200, row => {
        const v = info(row);
        return stacked(v.name ?? "商品待关联", v.sku ?? row.business_ref);
      }),
      col("kindSource", "采购类型 / 申请来源", 175, row => {
        const v = info(row);
        return stacked(kindText(v.kind), <Tag color={v.source === "system" ? "blue" : "default"}>{sourceText(v.source)}</Tag>);
      }),
      col("storeOwner", "店铺 / 负责人", 146, row => {
        const v = info(row);
        return stacked(v.store ?? "—", v.owner ?? "—");
      }),
      col("assessment", "采购评估", 185, row => {
        const v = info(row);
        if (v.kind === "initial") {
          return stacked(
            v.score == null ? "总分 —" : `总分 ${Number(v.score).toFixed(2)}`,
            v.grade ? <Tag color={v.grade === "S" || v.grade === "A" ? "blue" : v.grade === "D" || v.grade === "Pass" ? "red" : "default"}>
              {v.grade === "Pass" ? "Pass" : `${v.grade} 级`}
            </Tag> : "评级待确认",
          );
        }
        if (v.kind === "replenishment") {
          return stacked(
            v.days == null ? "预计可售 —" : `预计可售 ${v.days} 天`,
            v.sold30 == null ? "近30天销量 —" : `近30天销量 ${v.sold30} 件`,
          );
        }
        return "待评估";
      }),
      col("quantity", "建议量 / 申请量", 135, row => {
        const v = info(row);
        return stacked(`申请 ${qty(v.requested)}`, `建议 ${qty(v.suggested)}`);
      }),
      col("amount", "采购金额", 126, row => amountText(row)),
      common.risk,
      common.applicant,
      common.submitted,
      common.status,
      // PR337_PURCHASE_APPROVAL_ACTIONS_V2: match clearance approval table actions.
      col("action", "操作", 172, row => {
        // Demo rows may be exercised locally; real rows require server-issued can_review.
        const mayAct = row.status === "submitted" && Boolean(onAction) &&
          (row.id.startsWith("DEMO-") || row.can_review);
        return <div className="approval-clearance-actions">
          <Button type="link" size="small" onClick={() => onDetail(row)}>详情</Button>
          <Button type="link" size="small" disabled={!mayAct}
            onClick={() => onAction?.(row, "approve")}>通过</Button>
          <Button type="link" size="small" danger disabled={!mayAct}
            onClick={() => onAction?.(row, "reject")}>驳回</Button>
        </div>;
      }),
    ];
  }
  if (business === "clearance") {
    // V33: keep the original 12-column layout/labels/widths. Real values
    // come from clearance_details; demo records keep the original profile.
    type Live = {
      item_id?: string | null; sku?: string | null; msku?: string | null;
      store_name?: string | null; owner_ref?: string | null;
      methods?: string[] | null; requested_qty?: number | null;
      wfs_available_quantity?: string | number | null;
      listing_days?: number | null; inventory_cost_usd?: number | null;
    };
    const live = (row: ApprovalItem): Live | undefined =>
      (row as ApprovalItem & { clearance_details?: Live }).clearance_details;
    const clearanceSku = primaryClearanceSku;
    const actual = (row: ApprovalItem) => clearanceSku(row);
    const asNumber = (value: unknown): number | undefined => {
      if (value === null || value === undefined || value === "") return undefined;
      const n=Number(value);return Number.isFinite(n)?n:undefined;
    };
    const taskQuantity = (row: ApprovalItem) =>
      actual(row)?.target ?? asNumber(live(row)?.requested_qty);
    const available = (row: ApprovalItem) =>
      actual(row)?.available ?? asNumber(live(row)?.wfs_available_quantity);
    const riskLabel = (row: ApprovalItem) =>
      riskNames[row.risk_level] ?? (row.risk_level === "unknown" ? "待评估" : "无风险");
    return [
      col("title", "商品 ID / 品名", 205, (row) => {
        const item=actual(row), extra=live(row);
        return <div className="approval-clearance-cell approval-clearance-cell--product">
          <strong>{item?.name ?? row.title}</strong>
          <small>{item?.item ?? extra?.item_id ?? "—"}</small>
        </div>;
      }),
      col("sku", "SKU / MSKU", 155, (row) => {
        const item=actual(row), extra=live(row);
        return <div className="approval-clearance-cell">
          <strong>{item?.sku ?? extra?.sku ?? "—"}</strong>
          <small>{item?.msku ?? extra?.msku ?? "—"}</small>
        </div>;
      }),
      col("storeOwner", "店铺 / 负责人", 135, (row) => {
        const extra=live(row);
        return <div className="approval-clearance-cell">
          <strong>{extra?.store_name ?? row.source_account_ref ?? "—"}</strong>
          <small>{extra?.owner_ref ?? profile(row)?.owner ?? "—"}</small>
        </div>;
      }),
      col("risk", "风险等级", 90, (row) =>
        <Tag color={row.risk_level === "high" ? "red" : row.risk_level === "medium" ? "orange" : "default"}>{riskLabel(row)}</Tag>),
      col("submitted", "申请时间", 135, (row) => row.submitted_at
        ? new Date(row.submitted_at).toLocaleString("zh-CN", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}) : "—"),
      col("reason", "清货原因", 165, (row) =>
        <span className="approval-clearance-cell__reason" title={row.reason}>{row.reason || "—"}</span>),
      col("methods", "清货方式", 135, (row) =>
        live(row)?.methods?.join("、") ?? profile(row)?.methods?.join("、") ?? "—"),
      col("targetQty", "目标清货量", 105, (row) => quantity(taskQuantity(row))),
      col("stockListing", "WFS 可售 / 上架天数", 135, (row) => {
        const item=actual(row), extra=live(row);
        const days=item?.listingDays ?? asNumber(extra?.listing_days);
        return <div className="approval-clearance-cell">
          <strong>{quantity(available(row))}</strong>
          <small>上架天数：{days == null ? "—" : `${days.toLocaleString("zh-CN")} 天`}</small>
        </div>;
      }),
      col("inventoryCost", "库存成本", 115, (row) => {
        const item=actual(row), extra=live(row);
        return item ? money(item.available * item.cost) : money(extra?.inventory_cost_usd);
      }),
      col("status", "审批状态", 105, (row) =>
        <Tag color={row.status === "approved" ? "success" : row.status === "rejected" ? "error" : "processing"}>
          {titleByStatus[row.status] ?? row.status}
        </Tag>),
      col("action", "操作", 172, (row) => <div className="approval-clearance-actions">
        <Button type="link" size="small" onClick={() => onDetail(row)}>详情</Button>
        <Button type="link" size="small" disabled={row.status !== "submitted" || !row.can_review || !onAction}
          onClick={() => onAction?.(row,"approve")}>通过</Button>
        <Button type="link" size="small" danger disabled={row.status !== "submitted" || !row.can_review || !onAction}
          onClick={() => onAction?.(row,"reject")}>驳回</Button>
      </div>),
    ];
  }
  if (business === "listing") return [
    common.title,
    col("item", "商品ID", 140, r => profile(r)?.item ?? "—"),
    col("sku", "SKU / MSKU", 192, r => <><span>{profile(r)?.sku ?? "—"}</span><small className="approval-demo__subline">{profile(r)?.msku}</small></>),
    col("store", "店铺", 120, r => r.source_account_ref),
    col("listingStatus", "当前状态", 106, r => profile(r)?.listingStatus ?? "—"),
    common.risk, common.applicant, common.submitted, common.status, common.action,
  ];
  return [
    common.title,
    col("sku", "SKU / MSKU", 170, r => <><span>{profile(r)?.sku ?? "—"}</span><small className="approval-demo__subline">{profile(r)?.msku}</small></>),
    col("oldPrice", "原售价", 105, r => money(profile(r)?.oldPrice)),
    col("newPrice", "申请售价", 105, r => money(profile(r)?.newPrice)),
    col("priceDelta", "调整幅度", 107, r => {
      const n = delta(profile(r) ?? {kind:"price"});
      return n == null ? "—" : <Typography.Text type={n < 0 ? "danger" : "success"}>{n > 0 ? "+" : ""}{percent(n)}</Typography.Text>;
    }),
    col("priceMargin", "调整后利润率", 129, r => percent(profile(r)?.newMargin)),
    common.risk, common.applicant, common.status, common.action,
  ];
}
