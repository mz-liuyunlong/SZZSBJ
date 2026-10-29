/** Approved PKs only; reference stock and warehouse-owned packing remain separate. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Pagination, Select, Space, Tag, Tooltip, Typography } from "antd";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { CopyableTextCell, WalmartProductIdCell } from "@/components/report-table/cells";
import { packingWarehouseFields, type PackingWarehouseRow, type PackingWarehouseSort } from "./packingWarehouseTypes";
import { warehouseSyncLabel } from "./packingWarehouseApi";
export type WarehouseDialogKind = "boxes" | "done" | "notes" | "unpacked" | "rebox" | "supplemental-inbound" | "supplemental-sync" | "detail";
interface Props {
  pagination: { page: number; pageSize: number }; widths: Record<string, number>; sort: PackingWarehouseSort;
  rows: PackingWarehouseRow[]; total: number; loading: boolean; busy: boolean; customsDraft?: Record<string, boolean | null>;
  can: (kind: WarehouseDialogKind | "customs") => boolean; onAction: (row: PackingWarehouseRow, kind: WarehouseDialogKind) => void;
  onCustomsChange: (row: PackingWarehouseRow, value: boolean | null) => void;
  onPagination: (page: number, size: number) => void; onResize: (key: string, width: number) => void; onSort: (sort: PackingWarehouseSort) => void;
}
const copy = (value: string | null, label: string) => value ? <CopyableTextCell text={value} label={label} /> : "—";
export default function PackingWarehouseTable(p: Props) {
  const render = (key: string, row: PackingWarehouseRow) => {
    switch (key) {
      case "approved": return row.approved_date;
      case "draft": {
        const drafts = (row.draft_nos ?? []).map((value) => value.trim()).filter(Boolean);
        if (!drafts.length) return "—";
        return <Space direction="vertical" size={0}>{drafts.map((value) => <CopyableTextCell key={value} text={value} label="草稿号" />)}</Space>;
      }
      case "number": return <Space direction="vertical" size={0}>{copy(row.pk, "打包单号")}{row.is_test && <Tag>本地验证单</Tag>}</Space>;
      case "arrival": return <Tooltip title="与批次看板一致，采用入库业务日">{row.arrival_date ?? "日期未知"}</Tooltip>;
      case "received": return row.received_dates.length ? row.received_dates.join(" / ") : "待核实";
      case "inbound": return copy(row.inbound_order_sn, "入库单号");
      case "purchase": return <Space direction="vertical" size={0}>{row.purchase_order_sns.map((sn) => <CopyableTextCell key={sn} text={sn} label="采购单号" />)}</Space>;
      case "sku": return <Space direction="vertical" size={0}>{copy(row.sku, "SKU")}<Typography.Text type="secondary">{row.product_name ?? "—"}</Typography.Text></Space>;
      case "store": return row.store_name ?? row.store_id ?? "—";
      case "item": return <Space direction="vertical" size={0}>{row.item_id ? <WalmartProductIdCell productId={row.item_id} /> : "—"}<small>{row.msku ?? "—"}</small></Space>;
      case "gtin": return copy(row.gtin, "GTIN");
      case "quantity": return <Tooltip title="审批量 / 本单装箱量 / 来源批次当前余额；同来源余额不能跨PK累加">{row.approved_quantity} / {row.box_set?.total_qty ?? "—"} / {row.stock_balance ?? "未知"}</Tooltip>;
      case "boxes": return row.box_set ? <Space direction="vertical" size={0}>{row.box_set.lines.map((line) => <span key={line.id}>{line.box_type}箱 {line.boxes}×{line.units_per_box}件 · {line.gross_weight_kg}kg/箱</span>)}{row.box_set.variance_qty !== 0 && <Tag color="warning">{row.box_set.variance_qty < 0 ? `未装 ${Math.abs(row.box_set.variance_qty)} 件${row.variance_case?.state === "pending" ? " · 待中台处理" : row.variance_case?.state === "released" ? " · 已回可发池" : row.variance_case?.state === "voided" ? " · 已作废未装" : ""}` : `超出 ${row.box_set.variance_qty} 件`}</Tag>}</Space> : "未填装箱";
      case "status": return <Space direction="vertical" size={0}>
        {row.variance_case?.kind === "over" && row.variance_case.state === "blocked" && <><Tag color="orange">超发 {row.variance_case.quantity} 件 · 待补入库单</Tag><small>缺口 {row.variance_case.gap_qty ?? "待核实"} 件</small><small>{warehouseSyncLabel(row.variance_case.last_sync_code)}{row.variance_case.last_sync_gap ? `，仍差 ${row.variance_case.last_sync_gap} 件` : ""}</small><small>通知：本地待配置</small></>}
        {row.variance_case?.kind === "over" && row.variance_case.state === "ready" && <Tag color="green">已解除，请再次确认</Tag>}<Tag color={row.status === "packed" ? "purple" : "processing"}>{row.status === "packed" ? "已打包待发" : "待打包"}</Tag><small>领星箱规：未接入</small></Space>;
      case "days": return `${row.packing_days} / ${row.warehouse_days ?? "未知"} 天`;
      case "customs": {
        const shown = p.customsDraft && row.id in p.customsDraft ? p.customsDraft[row.id] : row.customs_value;
        const current = shown === true ? "declare" : shown === false ? "skip" : "unknown";
        return <Select className="domestic-packing__customs-select" size="small" aria-label={`是否报关 ${row.pk}`} disabled={p.busy || !p.can("customs")} value={current}
          options={[{ value: "declare", label: "报关" }, { value: "skip", label: "不报关" }, { value: "unknown", label: "未知" }]}
          onChange={(choice: "declare" | "skip" | "unknown") => { const next = choice === "declare" ? true : choice === "skip" ? false : null; if (next !== shown) p.onCustomsChange(row, next); }} />;
      }
      case "package": { const values = row.box_set?.package_snapshot?.values ?? row.product_requirement.package; return values ? <span>{values.length_cm}×{values.width_cm}×{values.height_cm} cm<br />毛重 {values.gross_weight_g} g</span> : <Tag color="warning">缺资料，仓库须补填</Tag>; }
      case "note": return row.current_note ? <Space direction="vertical" size={0}><Tag color={row.current_note.resolved ? "success" : "warning"}>{row.current_note.category_label}</Tag><span>{row.current_note.text}</span></Space> : "—";
      case "labels": return <Tooltip title="标签PDF不在本轮范围"><Button size="small" disabled>标签 PDF</Button></Tooltip>;
      default: return <Space wrap size={8}>
        <Button size="small" disabled={p.busy || !p.can("boxes") || row.status === "packed"} onClick={() => p.onAction(row, "boxes")}>{row.box_set ? "改装箱" : "填装箱"}</Button>
        {row.status === "packed" && p.can("rebox") && <Button size="small" disabled={p.busy || ["released", "voided"].includes(row.variance_case?.state ?? "")} onClick={() => p.onAction(row, "rebox")}>改装箱</Button>}
        <Tooltip title={(row.box_set?.variance_qty ?? 0) > 0 ? "完成时校验额外库存；余量不足则记录待补入库" : !row.box_set ? "请先保存装箱" : row.product_requirement.state !== "complete" ? "完成前须补填单品尺寸及毛重" : "确认装箱和包装资料"}><Button size="small" type="primary" disabled={p.busy || !p.can("done") || row.status === "packed" || !row.box_set} onClick={() => p.onAction(row, "done")}>打包完成</Button></Tooltip>
        {p.can("notes") && <Button size="small" disabled={p.busy} onClick={() => p.onAction(row, "notes")}>延迟备注</Button>}
        {p.can("unpacked") && row.variance_case?.kind === "under" && row.variance_case.state === "pending" && <Button size="small" disabled={p.busy} onClick={() => p.onAction(row, "unpacked")}>未装处置</Button>}
        {row.variance_case?.kind === "over" && row.variance_case.state === "blocked" && <>
          {p.can("supplemental-inbound") && <Button size="small" disabled={p.busy} onClick={() => p.onAction(row, "supplemental-inbound")}>已补入库单</Button>}
          {p.can("supplemental-sync") && <Button size="small" disabled={p.busy || !row.variance_case.supplemental_ib} onClick={() => p.onAction(row, "supplemental-sync")}>同步</Button>}
        </>}
        <Button size="small" onClick={() => p.onAction(row, "detail")}>详情</Button>
      </Space>;
    }
  };
  const columns: ProColumns<PackingWarehouseRow>[] = packingWarehouseFields.map((field) => {
    const width = field.key === "actions" ? Math.max(340, p.widths[field.key] ?? field.width) : p.widths[field.key] ?? field.width;
    return { key: field.key, dataIndex: field.key, width,
      title: <ResizableColumnTitle label={field.title} minWidth={field.key === "actions" ? 340 : 100} width={width} onWidthChange={(w) => p.onResize(field.key, w)} />,
      fixed: field.key === "number" ? "left" : field.key === "actions" ? "right" : undefined,
      sorter: field.key === "approved", sortOrder: field.key === "approved" ? p.sort === "approved_asc" ? "ascend" : "descend" : null,
      render: (_, row) => render(field.key, row) };
  });
  return <ReportTableShell label="仓库打包单表格"><ProTable<PackingWarehouseRow> rowKey="id" search={false} options={false} toolBarRender={false} tableAlertRender={false} size="small" bordered columns={columns} dataSource={p.rows} loading={p.loading}
    scroll={{ x: packingWarehouseFields.reduce((sum, field) => sum + (p.widths[field.key] ?? field.width), 0), y: "100%" }}
    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前条件下暂无已审批打包单" /> }}
    onChange={(_, __, sorter, extra) => { if (extra.action === "sort" && !Array.isArray(sorter)) p.onSort(sorter.order === "ascend" ? "approved_asc" : "approved_desc"); }} pagination={false} />
    <Pagination className="ant-table-pagination" size="small" current={p.pagination.page} pageSize={p.pagination.pageSize} total={p.total} showSizeChanger showQuickJumper pageSizeOptions={[20, 50, 100, 200]} showTotal={(n) => `共 ${n} 条`} onChange={(page, size) => p.onPagination(size !== p.pagination.pageSize ? 1 : page, size)} />
  </ReportTableShell>;
}
