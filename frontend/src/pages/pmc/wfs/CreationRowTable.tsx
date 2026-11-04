/**
 * 待创建货件单列表（Rocky 2026-11-04 第 12–16 条 + 拆票）：一行 = 一个打包单 × 一个货件。
 * 还没建的箱子每个打包单一行（待创建）；已提交的每票每个货件一行，打包单号在几行里重复。
 */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Checkbox, Dropdown, Modal, Space, Tag, Tooltip, Typography } from "antd";
import { useState } from "react";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import { WalmartItemLink } from "@/components/report-table/cells";
import EmptyState from "@/shared/states/EmptyState";
import { printCreationLabel, recoverCreation, retryCreation, type BoardRow, type RowStatus } from "./creationApi";
import { pendingError } from "./pendingPackingApi";
import type { PendingRow } from "./pendingPackingTypes";

const time = (v?: string | null) => v ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", dateStyle: "short", timeStyle: "short" }).format(new Date(v)) : "—";
const day = (v?: string | null) => v ? v.slice(0, 10) : "—";
const statusColor: Record<RowStatus, string> = {
  pending: "default", submitting: "processing", failed: "error", created: "success", shipped: "purple",
};
const printBlocked = (r: BoardRow) => {
  if (r.status !== "created" && r.status !== "shipped") return "创建成功、取到箱唛后才能打印";
  if (r.label_state === "FAILED") return "箱唛获取失败，请先点「补取」";
  if (r.label_state !== "READY") return "箱唛还在获取中";
  return undefined;
};

export interface RowActions {
  can: (key: string) => boolean;
  canDomestic: boolean;
  onIdentity: (row: PendingRow) => void;
  onRebox: (row: PendingRow) => void;
  onCustoms: (row: PendingRow) => void;
}

export default function CreationRowTable({ rows, total, loading, page, size, error, selected, onSelect, actions, onPageChange, onOpenRecords, onChanged, onError, onDone }: {
  rows: BoardRow[]; total: number; loading: boolean; page: number; size: number; error?: string;
  selected: string[]; onSelect: (ids: string[]) => void; actions: RowActions;
  onPageChange: (page: number, size: number) => void;
  onOpenRecords: (orderId: string) => void;
  onChanged: () => Promise<void>;
  onError: (text: string) => void;
  onDone: (text: string) => void;
}) {
  const [busy, setBusy] = useState<string>();
  const [modal, modalHolder] = Modal.useModal();
  const { can } = actions;
  const perform = async (key: string, action: () => Promise<unknown>, done?: string) => {
    setBusy(key);
    try { await action(); if (done) onDone(done); await onChanged(); return true; } catch (e) { onError(pendingError(e)); return false; } finally { setBusy(undefined); }
  };
  const retry = (r: BoardRow) => modal.confirm({
    title: `重试创建 · ${r.pk}`,
    content: "会先把这票的箱子重新占上，再用同一个单号去 Walmart 查一次；查到就直接记成功，查不到才重新提交。箱子已被别的货件占用时会拒绝。",
    okText: "确认重试",
    onOk: () => perform(r.key, () => retryCreation(r.ticket!.operation_id), "已提交重试"),
  });
  const toggle = (id: string, on: boolean) => onSelect(on ? [...selected, id] : selected.filter((x) => x !== id));
  const columns: ProColumns<BoardRow>[] = [
    { title: "选择", width: 56, fixed: "left", render: (_, r) => r.pending
      ? <Checkbox aria-label={`选择${r.pk}`} disabled={!r.pending.available_boxes || !!busy || !can("action:pmc:wfs-pending-packing:create")} checked={selected.includes(r.order_id)} onChange={(e) => toggle(r.order_id, e.target.checked)} />
      : null },
    { title: "状态", width: 150, fixed: "left", render: (_, r) => <span><Tag color={statusColor[r.status]} bordered={false}>{r.status_label}</Tag>{r.detail && <span className={r.status === "failed" ? "wfs-create__reason" : "wfs-create__sub"}>{r.detail}</span>}</span> },
    { title: "系统打包单", width: 170, fixed: "left", render: (_, r) => <span className="wfs-create__strong">{r.pk}{r.business_test && <Tag color="orange">测试</Tag>}{r.pending?.overdue && <Tag color="red">打包完成 {r.pending.packed_days} 天未建货件</Tag>}{r.ticket && <span className="wfs-create__sub">计划货件 {r.ticket.number}</span>}</span> },
    { title: "单号", width: 200, render: (_, r) => r.ticket?.inbound_order_id ?? <Typography.Text type="secondary">{r.ticket ? "提交后生成" : "—"}</Typography.Text> },
    { title: "货件号 · 目的 FC", width: 200, render: (_, r) => r.shipment_id ? <span><span className="wfs-create__strong">{r.shipment_id}</span><Tag bordered={false}>{r.fc ?? "FC 待返回"}</Tag></span> : "—" },
    { title: "发货单号", width: 150, render: (_, r) => r.shipping_code ?? "—" },
    { title: "箱唛", width: 170, render: (_, r) => {
      if (!r.ticket) return "—";
      const blocked = printBlocked(r);
      const ticket = r.ticket;
      return <span>
        <Space size={0}>
          <Tooltip title={blocked}><span><Button size="small" disabled={!!blocked || !!busy} loading={busy === `print:${r.key}`} onClick={() => void perform(`print:${r.key}`, () => printCreationLabel(ticket.operation_id, r.shipment_id!))}>打印箱唛</Button></span></Tooltip>
          {r.label_state === "FAILED" && can("action:pmc:wfs-pending-packing:label-retry") && <Button type="link" size="small" disabled={!!busy} onClick={() => void perform(`labels:${r.key}`, () => recoverCreation(ticket.operation_id, "labels/retry"), "已提交补取")}>补取</Button>}
        </Space>
        {r.print_count > 0 && <span className="wfs-create__sub">已打印（{r.print_count} 次）{r.printed_by ? ` · ${r.printed_by}` : ""}</span>}
      </span>;
    } },
    { title: "店铺", width: 150, render: (_, r) => r.store_name ?? r.store_id ?? "—" },
    { title: "SKU · 品名", width: 180, render: (_, r) => <span>{r.sku ?? "—"}<span className="wfs-create__sub">{r.product_name ?? "—"}</span></span> },
    { title: "Item ID / GTIN", width: 160, render: (_, r) => <span><WalmartItemLink itemId={r.item_id} /><span className="wfs-create__sub">{r.gtin ?? "缺GTIN"}</span></span> },
    { title: "箱 / 件", width: 100, align: "right", render: (_, r) => r.pending ? `${r.pending.available_boxes} / ${r.pending.available_units}` : r.ticket ? `${r.ticket.boxes} / ${r.ticket.units}` : "—" },
    { title: "预计到仓", width: 100, render: (_, r) => day(r.ticket?.expected_delivery_at) },
    { title: "提交人", width: 170, render: (_, r) => {
      if (r.pending) return <span>{r.pending.order.box_set?.completed_by ?? "—"}<span className="wfs-create__sub">打包完成 {time(r.pending.order.box_set?.completed_at)}</span></span>;
      const t = r.ticket!;
      return <span>{t.created_by}<span className="wfs-create__sub">确认创建 {time(t.created_at)}</span></span>;
    } },
    { title: "操作", width: 150, fixed: "right", render: (_, r) => <Space size={0}>
      {r.status === "failed" && can("action:pmc:wfs-pending-packing:create") && <Button type="link" size="small" loading={busy === r.key} disabled={!!busy} onClick={() => retry(r)}>重试</Button>}
      {r.pending && (() => {
        const p = r.pending;
        const items = [
          actions.canDomestic && can("action:pmc:domestic-warehouse-board:packing-rebox") && { key: "rebox", label: "改装箱", disabled: !p.can_edit || !!busy, onClick: () => actions.onRebox(p) },
          actions.canDomestic && can("action:pmc:domestic-warehouse-board:packing-customs") && { key: "customs", label: "修改报关", disabled: !p.can_edit || !!busy, onClick: () => actions.onCustoms(p) },
          can("action:pmc:wfs-pending-packing:identity-switch") && { key: "identity", label: "换店铺 / 换链接", disabled: !p.can_edit || !!busy, onClick: () => actions.onIdentity(p) },
        ].filter((x): x is { key: string; label: string; disabled: boolean; onClick: () => void } => !!x);
        return items.length ? <Dropdown menu={{ items }} trigger={["click"]}><Button type="link" size="small">更多</Button></Dropdown> : null;
      })()}
      <Button type="link" size="small" onClick={() => onOpenRecords(r.order_id)}>创建记录</Button>
    </Space> },
  ];
  return <ReportTableShell label="待创建货件表格" className="wfs-create__table-shell">
    {modalHolder}
    <ProTable<BoardRow>
      rowKey="key" search={false} options={false} toolBarRender={false} tableAlertRender={false}
      size="small" bordered columns={columns} dataSource={rows} loading={loading}
      scroll={{ x: columns.reduce((n, c) => n + Number(c.width ?? 120), 0), y: "100%" }}
      locale={{ emptyText: <EmptyState title={error ? "数据未加载" : "暂无数据"} description={error ?? "当前条件下没有货件"} compact /> }}
      pagination={{
        current: page, pageSize: size, total, showSizeChanger: true, pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
        showTotal: (n) => `共 ${n} 行`,
        onChange: (next, nextSize) => onPageChange(nextSize !== size ? 1 : next, nextSize),
      }}
    />
  </ReportTableShell>;
}
