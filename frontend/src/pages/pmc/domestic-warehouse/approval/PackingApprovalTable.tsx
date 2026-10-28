import PackingCustomsSelect from "./PackingCustomsSelect";
import { useState } from "react";
import { customsHint, customsSourceLabel, type CustomsChoice } from "./packingCustoms";
/** Published approval candidates with explicit blocking and server pagination. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Pagination, Space, Tag, Tooltip, Typography } from "antd";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { CopyableTextCell, WalmartItemLink } from "@/components/report-table/cells";
import { packingApprovalFields, type PackingApprovalSort } from "./packingApprovalTypes";
import { approvalBlockedText, type ApprovalCandidate, type DecisionKind } from "./packingApprovalApi";

function copyOrDash(text: string | null | undefined, label: string) {
  const value = text?.trim();
  return value ? <CopyableTextCell text={value} label={label} /> : "—";
}

function purchaseCopies(orderSns: string[], label = "采购单号") {
  const values = orderSns.map((sn) => sn.trim()).filter(Boolean);
  if (!values.length) return "—";
  if (values.length === 1) return <CopyableTextCell text={values[0]} label={label} />;
  return (
    <Space direction="vertical" size={0} className="report-table-identity-stack">
      {values.map((sn) => (
        <CopyableTextCell key={sn} text={sn} label={label} />
      ))}
    </Space>
  );
}
interface Props {
  pagination: { page: number; pageSize: number }; widths: Record<string, number>; sort: PackingApprovalSort;
  rows: ApprovalCandidate[]; total: number; canApprove: boolean; canReject: boolean; busy: boolean;
  onDecision: (row: ApprovalCandidate, kind: DecisionKind) => void;
  onApprove: (row: ApprovalCandidate) => void;
  onPagination: (page: number, pageSize: number) => void; onResize: (key: string, width: number) => void;
  onSort: (sort: PackingApprovalSort) => void;
}
export default function PackingApprovalTable(p: Props) {
  const [customs, setCustoms] = useState<Record<string, CustomsChoice>>({});
  const choiceOf = (row: ApprovalCandidate) => customs[`${row.id}|${row.candidate_version}`] ?? row.manual_customs ?? "default";
  const withChoice = (row: ApprovalCandidate): ApprovalCandidate => ({ ...row, manual_customs: choiceOf(row) });
  const show = (key: string, row: ApprovalCandidate) => {
    const values: Record<string, string | number | null> = { msku: row.msku, store: row.store_name ?? row.store_id, qty: row.available_quantity };
    if (key === "number") return <Space direction="vertical" size={0}><Typography.Text type="secondary">{row.origin === "manual" ? "手工待审批（未发PK）" : "待审批（未发PK）"}</Typography.Text>{row.edit_draft_pending && <Tag color="gold">已修改未审批</Tag>}<small>{row.candidate_created_on ?? "日期未知"}</small></Space>;
    if (key === "draft") return purchaseCopies(row.draft_nos ?? [], "草稿号");
    if (key === "inbound") return copyOrDash(row.inbound_order_sn, "入库单号");
    if (key === "purchase") return purchaseCopies(row.purchase_order_sns);
    if (key === "sku") return copyOrDash(row.sku, "SKU");
    if (key === "gtin") return copyOrDash(row.gtin, "GTIN");
    if (key === "item") return <WalmartItemLink itemId={row.item_id} />;
    if (key === "arrival") return <Space direction="vertical" size={0}><Tooltip title="采购单明细累计数量；跨 ItemID 重复展示，不可累加；当前可打包库存另列">{row.arrival_purchased ?? "—"} / {row.arrival_received ?? "—"} / {row.arrival_pending ?? "—"}</Tooltip><Tag>{({ full: "已全部到货", partial: "部分到货", none: "未到货", unknown: "到货明细未知" })[row.arrival_status]}</Tag></Space>;
    if (key === "batches") return <Tooltip title="仅按当前发布入库单识别；不代表完整历史"><Space direction="vertical" size={0}><Tag>{row.split_arrival === true ? "已观测分批" : row.split_arrival === false ? "单批已到齐" : "分批情况未知"}</Tag>{row.arrival_batch_count ? <small>{row.arrival_batch_index ? `第 ${row.arrival_batch_index} 批 / ` : "已观测 "}{row.arrival_batch_count} 批</small> : null}</Space></Tooltip>;
    if (key === "qty") return <Tooltip title={[row.quantity_suggestion?.rule === "plan_ratio" ? "按采购计划比例预填，可人工修改" : "人工确认数量后审批", ...(row.quantity_suggestion?.notes ?? [])].join("；")}><Space direction="vertical" size={0}><span>{row.default_quantity ?? "待填写"} / {row.available_quantity ?? "—"}</span><small>{row.quantity_suggestion?.rule === "plan_ratio" ? "计划比例建议" : "人工确认"}</small></Space></Tooltip>;
    if (key === "customs") {
      const choice = choiceOf(row);
      return <Space className="domestic-approval__customs-cell" direction="vertical" size={0}><PackingCustomsSelect row={row} size="small" aria-label={`是否报关 ${row.inbound_order_sn} ${row.item_id ?? row.id}`} value={choice} disabled={!p.canApprove || p.busy}
        onChange={(value: CustomsChoice) => setCustoms((previous) => ({ ...previous, [`${row.id}|${row.candidate_version}`]: value }))} />
        <Tooltip title={customsHint(row, choice)}><Tag>{customsSourceLabel(choice === "default" ? row.customs_default_src ?? "default" : "manual")}</Tag></Tooltip></Space>;
    }
    if (key === "waiting") return row.waiting_days ?? "—";
    if (key === "coverage") return row.history_complete ? "完整" : "部分历史";
    if (key === "status") return <Tooltip title={approvalBlockedText(row.blocked_reasons)}><Tag color={row.can_approve ? "processing" : "warning"}>{row.can_approve ? "待审批" : "待补资料"}</Tag>{row.overdue && <Tag color="red">超时</Tag>}</Tooltip>;
    if (key === "actions") return <Space className="domestic-approval__row-actions" size={12}><Button className="domestic-approval__row-edit" size="small" disabled={!p.canApprove || p.busy} onClick={() => p.onDecision(withChoice(row), "approve")}>修改</Button></Space>;
    return values[key] ?? "—";
  };
  const widthOf = (key: string, fallback: number) => key === "actions" ? Math.max(96, p.widths[key] ?? fallback) : p.widths[key] ?? fallback;
  const columns: ProColumns<ApprovalCandidate>[] = packingApprovalFields.map((field) => ({
    key: field.key, dataIndex: field.key, width: widthOf(field.key, field.width),
    title: <ResizableColumnTitle label={field.title} minWidth={field.key === "actions" ? 96 : 90} width={widthOf(field.key, field.width)} onWidthChange={(w) => p.onResize(field.key, w)} />,
    fixed: field.key === "number" ? "left" : field.key === "actions" ? "right" : undefined,
    sorter: field.key === "number", sortOrder: field.key === "number" ? (p.sort === "created_asc" ? "ascend" : "descend") : null,
    render: (_, row) => show(field.key, row),
  }));
  return <ReportTableShell label="打包单审批表格"><ProTable<ApprovalCandidate> rowKey="id" search={false} options={false} toolBarRender={false}
    tableAlertRender={false} size="small" bordered columns={columns} dataSource={p.rows} loading={false}
    scroll={{ x: 2210, y: "100%" }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前条件下暂无待审批单据" /> }}
    onChange={(_, __, sorter, extra) => { if (extra.action === "sort" && !Array.isArray(sorter)) p.onSort(sorter.order === "ascend" ? "created_asc" : "created_desc"); }} pagination={false} />
    <Pagination className="ant-table-pagination" size="small" current={p.pagination.page} pageSize={p.pagination.pageSize} total={p.total} showSizeChanger showQuickJumper pageSizeOptions={[20, 50, 100, 200]} showTotal={(n) => `共 ${n} 条`} onChange={(page, size) => p.onPagination(size !== p.pagination.pageSize ? 1 : page, size)} />
  </ReportTableShell>;
}
