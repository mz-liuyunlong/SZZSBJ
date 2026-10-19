/** Empty structural table: actions remain disabled until approved backend capabilities exist. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Pagination, Space, Tag, Tooltip, Typography } from "antd";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { CopyableTextCell, WalmartItemLink } from "@/components/report-table/cells";
import { packingWarehouseFields, type PackingWarehouseRow, type PackingWarehouseSort } from "./packingWarehouseTypes";

interface Props {
  pagination: { page: number; pageSize: number };
  widths: Record<string, number>;
  sort: PackingWarehouseSort;
  onPagination: (page: number, pageSize: number) => void;
  onResize: (key: string, width: number) => void;
  onSort: (sort: PackingWarehouseSort) => void;
}

function DisabledPackingActions({ labelsOnly = false }: { labelsOnly?: boolean }) {
  return <Tooltip title={labelsOnly ? "标签 PDF 服务尚未接入" : "装箱保存与完成接口尚未接入"}>
    <span><Space size={8}>{labelsOnly ? <Button size="small" disabled>标签 PDF</Button> : <>
      <Button size="small" disabled>填装箱</Button><Button size="small" disabled>打包完成</Button>
    </>}</Space></span>
  </Tooltip>;
}

function renderPackingCell(key: string, row: PackingWarehouseRow) {
  switch (key) {
    case "approved": return row.approvedDate ?? "—";
    case "number": return row.packingNumber
      ? <div className="domestic-packing__stack"><CopyableTextCell text={row.packingNumber} label="打包单号" /><Typography.Text type="secondary">系统打包单</Typography.Text></div>
      : <Tag color="warning">领星人工单</Tag>;
    // Keep every receipt date when multiple arrivals are combined; never substitute inbound dates.
    case "received": return row.receipts.length ? <div className="domestic-packing__stack">{row.receipts.map((receipt) =>
      <Tooltip key={receipt.receiptOrderSn} title={`收货单：${receipt.receiptOrderSn}`}>
        <span>{receipt.receivedDate ?? "待核实"}</span>
      </Tooltip>)}</div> : "待核实";
    case "inbound": return row.inboundOrderSns.join(" / ") || <Typography.Text type="secondary">未关联</Typography.Text>;
    case "purchase": return row.purchaseOrderSns.join(" / ") || "—";
    case "sku": return <div className="domestic-packing__stack"><Typography.Text strong>{row.sku ?? "—"}</Typography.Text>
      <Typography.Text type="secondary" ellipsis={{ tooltip: row.productName }}>{row.productName ?? "—"}</Typography.Text></div>;
    case "store": return row.storeName ?? "—";
    case "item": return row.itemId ? <div className="domestic-packing__stack"><WalmartItemLink itemId={row.itemId} />
      <Typography.Text type="secondary">{row.msku ?? "—"}</Typography.Text></div> : <Typography.Text type="secondary">待归属</Typography.Text>;
    case "gtin": return row.gtin ? <CopyableTextCell text={row.gtin} label="GTIN" /> : "—";
    case "labels": return <DisabledPackingActions labelsOnly />;
    default: return <DisabledPackingActions />;
  }
}

export default function PackingWarehouseTable({ pagination, widths, sort, onPagination, onResize, onSort }: Props) {
  const columns: ProColumns<PackingWarehouseRow>[] = packingWarehouseFields.map((field) => {
    const sortPrefix = field.key === "approved" ? "approved" : field.key === "received" ? "received" : undefined;
    return {
      key: field.key, dataIndex: field.key, width: widths[field.key] ?? field.width,
      title: <ResizableColumnTitle label={field.title} minWidth={100} width={widths[field.key] ?? field.width}
        onWidthChange={(width) => onResize(field.key, width)} />,
      onHeaderCell: () => ({ className: "report-table-resizable-header-cell" }),
      fixed: field.key === "approved" || field.key === "number" ? "left" : field.key === "actions" || field.key === "labels" ? "right" : undefined,
      sorter: Boolean(sortPrefix), ellipsis: !["sku", "item", "received"].includes(field.key),
      sortOrder: sortPrefix && sort.startsWith(sortPrefix) ? (sort.endsWith("asc") ? "ascend" : "descend") : null,
      render: (_, row) => renderPackingCell(field.key, row),
    };
  });
  return <ReportTableShell label="仓库打包单表格">
    <ProTable<PackingWarehouseRow> rowKey="id" search={false} options={false} toolBarRender={false}
      tableAlertRender={false} size="small" bordered columns={columns} dataSource={[]}
      scroll={{ x: packingWarehouseFields.reduce((sum, field) => sum + (widths[field.key] ?? field.width), 0), y: "100%" }}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="打包单查询服务尚未接入，暂不展示业务数据">
        <Space wrap><DisabledPackingActions labelsOnly /><DisabledPackingActions /></Space>
      </Empty> }}
      onChange={(_, __, sorter, extra) => {
        if (extra.action !== "sort" || Array.isArray(sorter)) return;
        const field = sorter.columnKey === "received" ? "received" : "approved";
        onSort(`${field}_${sorter.order === "ascend" ? "asc" : "desc"}`);
      }}
      pagination={false} />
    {/* Ant Table omits pagination at total=0; retain a real, zero-total pager for this structural page. */}
    <Pagination className="ant-table-pagination" size="small" current={pagination.page} pageSize={pagination.pageSize} total={0}
      hideOnSinglePage={false} showSizeChanger showQuickJumper pageSizeOptions={[20, 50, 100, 200]}
      showTotal={() => "查询服务未接入"}
      onChange={(page, size) => onPagination(size !== pagination.pageSize ? 1 : page, size)} />
  </ReportTableShell>;
}
