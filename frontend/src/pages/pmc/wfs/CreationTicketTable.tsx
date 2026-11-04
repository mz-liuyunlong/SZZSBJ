/** 提交中 / 创建失败 / 已创建未发货：一行一票（计划货件），ReportTableShell + ProTable。 */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Modal, Space, Tag, Typography } from "antd";
import { useState } from "react";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import EmptyState from "@/shared/states/EmptyState";
import { downloadCreationLabel, retryCreation, type TicketRow, type TicketTab } from "./creationApi";
import { pendingError } from "./pendingPackingApi";

const time = (v?: string | null) => v ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", dateStyle: "short", timeStyle: "short" }).format(new Date(v)) : "—";
const day = (v?: string | null) => v ? v.slice(0, 10) : "—";
const emptyText: Record<TicketTab, string> = {
  submitting: "没有提交中的货件",
  failed: "没有创建失败的货件",
  created: "没有已创建未发货的货件",
};

export default function CreationTicketTable({ tab, rows, total, loading, page, size, error, canRetry, onPageChange, onOpenRecords, onChanged, onError }: {
  tab: TicketTab; rows: TicketRow[]; total: number; loading: boolean; page: number; size: number;
  error?: string; canRetry: boolean;
  onPageChange: (page: number, size: number) => void;
  onOpenRecords: (orderId: string) => void;
  onChanged: () => Promise<void>;
  onError: (text: string) => void;
}) {
  const [busy, setBusy] = useState<string>();
  const [modal, modalHolder] = Modal.useModal();
  const perform = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    try { await action(); await onChanged(); } catch (e) { onError(pendingError(e)); } finally { setBusy(undefined); }
  };
  const retry = (row: TicketRow) => modal.confirm({
    title: `重试创建 · ${row.pks.join("、")}`,
    content: "会先把这票的箱子重新占上，再用同一个单号去 Walmart 查一次；查到就直接记成功，查不到才重新提交。箱子已被别的货件占用时会拒绝。",
    okText: "确认重试",
    onOk: () => perform(row.ticket_id, () => retryCreation(row.operation_id)),
  });
  const base: ProColumns<TicketRow>[] = [
    { title: "打包单 PK · 单号", width: 230, fixed: "left", render: (_, r) => <span className="wfs-create__strong">{r.pks.join("、") || "—"}<span className="wfs-create__sub">计划货件 {r.number}{r.inbound_order_id ? ` · 单号 ${r.inbound_order_id}` : ""}</span></span> },
    { title: "店铺", width: 160, render: (_, r) => r.store_name ?? r.store_id ?? "—" },
    { title: "SKU", width: 150, render: (_, r) => r.skus.join("、") || "—" },
    { title: "箱 / 件", width: 90, align: "right", render: (_, r) => `${r.boxes} / ${r.units}` },
  ];
  const created: ProColumns<TicketRow> = { title: "提交", width: 150, render: (_, r) => <span>{r.created_by}<span className="wfs-create__sub">{time(r.created_at)}</span></span> };
  const approved: ProColumns<TicketRow> = { title: "批准", width: 200, render: (_, r) => r.approved_at ? <span>{r.approved_by} · {time(r.approved_at)}<span className="wfs-create__ref">{r.approval_ref}</span></span> : <Typography.Text type="secondary">待人工批准</Typography.Text> };
  const records: ProColumns<TicketRow> = { title: "操作", width: 110, fixed: "right", render: (_, r) => <Button type="link" size="small" onClick={() => onOpenRecords(r.order_id)}>创建记录</Button> };
  const byTab: Record<TicketTab, ProColumns<TicketRow>[]> = {
    submitting: [
      { title: "状态", width: 190, fixed: "left", render: (_, r) => <Tag color={r.awaiting_approval ? "gold" : "processing"} bordered={false}>{r.status_label}</Tag> },
      ...base,
      { title: "查询进度", width: 170, render: (_, r) => r.polls === null ? "—" : <span>已查询 {r.polls}/{r.max_polls} 次<span className="wfs-create__sub">下次 {time(r.next_poll_at)}</span></span> },
      approved, created, records,
    ],
    failed: [
      { title: "失败原因", width: 320, fixed: "left", render: (_, r) => <span><Tag color="error" bordered={false}>{r.status_label}</Tag><span className="wfs-create__reason">{r.error_message ?? r.error_code ?? "—"}</span></span> },
      ...base,
      { title: "已提交次数", width: 96, align: "right", render: (_, r) => r.submissions },
      approved, created,
      { title: "操作", width: 150, fixed: "right", render: (_, r) => <Space size={0}>
        {canRetry && <Button type="link" size="small" loading={busy === r.ticket_id} disabled={!!busy} onClick={() => retry(r)}>重试</Button>}
        <Button type="link" size="small" onClick={() => onOpenRecords(r.order_id)}>创建记录</Button>
      </Space> },
    ],
    created: [
      { title: "货件号 · 目的 FC", width: 260, fixed: "left", render: (_, r) => r.shipments.length ? r.shipments.map((s) => <span key={s.shipment_id} className="wfs-create__shipment"><span className="wfs-create__strong">{s.shipment_id}</span><Tag bordered={false}>{s.fc ?? "FC 待返回"}</Tag></span>) : "—" },
      ...base,
      { title: "箱唛", width: 200, render: (_, r) => r.shipments.map((s) => <span key={s.shipment_id} className="wfs-create__sub">{s.label_state === "READY"
        ? <Button type="link" size="small" disabled={!!busy} onClick={() => void perform(`${r.ticket_id}:${s.shipment_id}`, () => downloadCreationLabel(r.operation_id, s.shipment_id))}>下载箱唛 {s.shipment_id.slice(-6)}</Button>
        : s.label_state === "FAILED" ? "获取失败，可在创建记录补取" : "待获取"}</span>) },
      { title: "预计到仓", width: 110, render: (_, r) => day(r.expected_delivery_at) },
      approved, created, records,
    ],
  };
  const columns = byTab[tab];
  return <ReportTableShell label={`${{ submitting: "提交中", failed: "创建失败", created: "已创建未发货" }[tab]}表格`} className="wfs-create__table-shell">
    {modalHolder}
    <ProTable<TicketRow>
      rowKey="ticket_id" search={false} options={false} toolBarRender={false} tableAlertRender={false}
      size="small" bordered columns={columns} dataSource={rows} loading={loading}
      scroll={{ x: columns.reduce((n, c) => n + Number(c.width ?? 120), 0), y: "100%" }}
      locale={{ emptyText: <EmptyState title={error ? "数据未加载" : "暂无数据"} description={error ?? emptyText[tab]} compact /> }}
      pagination={{
        current: page, pageSize: size, total, showSizeChanger: true, pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
        showTotal: (n) => `共 ${n} 票`,
        onChange: (next, nextSize) => onPageChange(nextSize !== size ? 1 : next, nextSize),
      }}
    />
  </ReportTableShell>;
}
