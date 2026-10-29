/** V3 demo-only business-specific columns and evidence. Never used for WFS cases. */
import { Button, Tag, Typography } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import type { ReactNode } from "react";
import type { ApprovalItem } from "./approvalTypes";
import type { ApprovalBusinessKey } from "./approvalBusiness";

export interface ClearanceSku {
  sku: string; msku: string; item: string; name: string;
  available: number; age: number; target: number; cost: number;
  price: number; rating: number; returnRate: number;
  sales: [number, number, number];
  revenue: [number, number, number];
  ad: [number, number, number];
  profit: [number, number, number];
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
  "DEMO-PO-001": { kind: "purchase", supplier: "演示·深圳包装供应商", quantity: 240, delivery: "2026-11-10", owner: "演示运营A", sku: "DEMO-SKU-101", product: "厨房收纳盒套装" },
  "DEMO-PO-002": { kind: "purchase", supplier: "演示·东莞五金供应商", quantity: 600, delivery: "2026-11-05", owner: "演示运营B", sku: "DEMO-SKU-102", product: "厨房不锈钢压泥器" },
  "DEMO-PO-003": { kind: "purchase", supplier: "演示·深圳塑胶供应商", quantity: 180, delivery: "2026-11-18", owner: "演示运营C", sku: "DEMO-SKU-103", product: "抽屉分格收纳盒" },
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

const money = (value: number | string | null | undefined) => value == null ? "—" : `$${Number(value).toFixed(2)}`;
const quantity = (value: number | undefined) => value == null ? "—" : `${value.toLocaleString("zh-CN")} 件`;
const percent = (n: number | undefined) => n == null ? "—" : `${n.toFixed(1)}%`;
const delta = (p: DemoBusinessProfile) => p.oldPrice && p.newPrice != null ? (p.newPrice - p.oldPrice) / p.oldPrice * 100 : null;
const titleByStatus: Record<string, string> = { submitted: "待审批", approved: "已审批", rejected: "驳回记录" };
const riskNames: Record<string, string> = { low: "低风险", medium: "中风险", high: "高风险" };

function col(key: string, title: string, width: number, cell: (r: ApprovalItem) => ReactNode): ProColumns<ApprovalItem> {
  return { key, title, width, render: (_value, row) => cell(row) };
}

/** Independent columns mirror SPEC in the uploaded V3 HTML demo. */
export function demoColumnsForBusiness(
  business: ApprovalBusinessKey,
  onDetail: (item: ApprovalItem) => void,
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
  if (business === "purchase") return [
    common.title,
    col("supplier", "供应商", 178, r => profile(r)?.supplier ?? "—"),
    col("qty", "采购数量", 100, r => quantity(profile(r)?.quantity)),
    col("due", "要求交期", 115, r => profile(r)?.delivery ?? "—"),
    col("amount", "采购金额", 119, r => money(r.amount)),
    common.risk, common.applicant, common.status, common.action,
  ];
  if (business === "clearance") return [
    common.title,
    col("store", "店铺", 121, r => r.source_account_ref),
    col("qty", "清货目标", 105, r => quantity(profile(r)?.targetQty)),
    col("methods", "清货方式", 145, r => profile(r)?.methods?.join("、") ?? "—"),
    col("amount", "库存成本", 114, r => {
      const ps = profile(r)?.clearanceSkus ?? [];
      return money(ps.reduce((sum, p) => sum + p.target * p.cost, 0));
    }),
    common.risk, common.applicant, common.submitted, common.status, common.action,
  ];
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

