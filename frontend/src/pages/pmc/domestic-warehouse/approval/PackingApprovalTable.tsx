/** Published approval candidates with explicit blocking and server pagination. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Pagination, Space, Tag, Tooltip, Typography } from "antd";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { packingApprovalFields, type PackingApprovalSort } from "./packingApprovalTypes";
import { approvalBlockedText, type ApprovalCandidate, type DecisionKind } from "./packingApprovalApi";
interface Props {
  pagination: { page: number; pageSize: number }; widths: Record<string, number>; sort: PackingApprovalSort;
  rows: ApprovalCandidate[]; total: number; loading: boolean; canApprove: boolean; canReject: boolean; busy: boolean;
  onDecision: (row: ApprovalCandidate, kind: DecisionKind) => void;
  onPagination: (page: number, pageSize: number) => void; onResize: (key: string, width: number) => void;
  onSort: (sort: PackingApprovalSort) => void;
}
export default function PackingApprovalTable(p: Props) {
  const show = (key: string, row: ApprovalCandidate) => {
    const values: Record<string, string | number | null> = { number: row.candidate_created_on, inbound: row.inbound_order_sn, purchase: row.purchase_order_sns.join(" / "), sku: row.sku, gtin: row.gtin, item: row.item_id, msku: row.msku, store: row.store_name ?? row.store_id, qty: row.available_quantity };
    if (key === "number") return <Space direction="vertical" size={0}><Typography.Text type="secondary">待审批（未发PK）</Typography.Text><small>{row.candidate_created_on ?? "日期未知"}</small></Space>;
    if (key === "arrival") return <Tooltip title="收货明细尚未标准化，已到/未到保持未知">{row.arrival_purchased ?? "—"} / {row.arrival_received ?? "—"} / {row.arrival_pending ?? "—"}</Tooltip>;
    if (key === "customs") return "审批时选择";
    if (key === "status") return <Tooltip title={approvalBlockedText(row.blocked_reasons)}><Tag color={row.can_approve ? "processing" : "warning"}>{row.can_approve ? "待审批" : "待补资料"}</Tag>{row.overdue && <Tag color="red">超时</Tag>}</Tooltip>;
    if (key === "actions") return <Space><Tooltip title={!p.canApprove ? "缺少审批通过权限" : approvalBlockedText(row.blocked_reasons)}><Button size="small" disabled={!p.canApprove || !row.can_approve || p.busy} onClick={() => p.onDecision(row, "approve")}>通过</Button></Tooltip><Button size="small" disabled={!p.canReject || p.busy} onClick={() => p.onDecision(row, "reject")}>驳回</Button></Space>;
    return values[key] ?? "—";
  };
  const columns: ProColumns<ApprovalCandidate>[] = packingApprovalFields.map((field) => ({
    key: field.key, dataIndex: field.key, width: p.widths[field.key] ?? field.width,
    title: <ResizableColumnTitle label={field.title} minWidth={90} width={p.widths[field.key] ?? field.width} onWidthChange={(w) => p.onResize(field.key, w)} />,
    fixed: field.key === "number" ? "left" : field.key === "actions" ? "right" : undefined,
    sorter: field.key === "number", sortOrder: field.key === "number" ? (p.sort === "created_asc" ? "ascend" : "descend") : null,
    render: (_, row) => show(field.key, row),
  }));
  return <ReportTableShell label="打包单审批表格"><ProTable<ApprovalCandidate> rowKey="id" search={false} options={false} toolBarRender={false}
    tableAlertRender={false} size="small" bordered columns={columns} dataSource={p.rows} loading={p.loading}
    scroll={{ x: 2050, y: "100%" }} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前条件下暂无待审批单据" /> }}
    onChange={(_, __, sorter, extra) => { if (extra.action === "sort" && !Array.isArray(sorter)) p.onSort(sorter.order === "ascend" ? "created_asc" : "created_desc"); }} pagination={false} />
    <Pagination className="ant-table-pagination" size="small" current={p.pagination.page} pageSize={p.pagination.pageSize} total={p.total} showSizeChanger showQuickJumper pageSizeOptions={[20, 50, 100, 200]} showTotal={(n) => `共 ${n} 条`} onChange={(page, size) => p.onPagination(size !== p.pagination.pageSize ? 1 : page, size)} />
  </ReportTableShell>;
}
