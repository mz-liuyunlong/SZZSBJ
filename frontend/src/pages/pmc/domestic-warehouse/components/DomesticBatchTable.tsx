/** Receipt-line table shares the purchase board's scrolling, resizing and pagination frame. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Tag, Tooltip, Typography } from "antd";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { CopyableTextCell } from "@/components/report-table/cells";
import EmptyState from "@/shared/states/EmptyState";
import { domesticColumns, formatQuantity, type BatchSort, type DomesticBatch } from "../domesticWarehouseTypes";

interface Props {
  rows: DomesticBatch[]; total: number; loading: boolean;
  columns: { keys: string[]; widths: Record<string, number> };
  pagination: { page: number; pageSize: number };
  sort: BatchSort;
  onPagination: (page: number, size: number) => void;
  onSort: (sort: BatchSort) => void;
  onResize: (key: string, width: number) => void;
  onDetail: (id: string) => void;
}
const ids = (values: (string | null)[]) => [...new Set(values.filter((v): v is string => Boolean(v)))].join(" / ") || "—";
const missing = <Tooltip title="当前只读接口尚未提供该字段"><Typography.Text type="secondary">—</Typography.Text></Tooltip>;
function renderCell(key: string, row: DomesticBatch) {
  switch (key) {
    case "arrival": return row.received_business_date
      ? <Tooltip title={`收货单 ${row.receipt_order_sn} 的实际收货日期`}>{row.received_business_date}</Tooltip>
      : <Tag color="warning">待核实</Tag>;
    case "inbound": return ids(row.links.map((link) => link.batch_order_sn));
    case "receipt": return <CopyableTextCell text={row.receipt_order_sn} label="收货单号" />;
    case "purchase": return row.purchase_order_sn ? <CopyableTextCell text={row.purchase_order_sn} label="采购单号" /> : "—";
    case "sku": return row.sku ? <Typography.Text strong>{row.sku}</Typography.Text> : "—";
    case "store": return ids(row.links.map((link) => link.store_id));
    case "age": return row.days_in_warehouse === null ? "—" : `${row.days_in_warehouse} 天`;
    case "quantity": return formatQuantity(row.received_qty);
    case "warehouse": return row.source_warehouse_id ?? "—";
    case "mapping": return <Tag color={row.mapping_status === "matched" ? "success" : "warning"}>
      {row.mapping_status === "matched" ? "库存已关联" : "库存待关联"}</Tag>;
    default: return missing;
  }
}
export default function DomesticBatchTable({ rows, total, loading, columns: settings, pagination, sort, onPagination, onSort, onResize, onDetail }: Props) {
  const columns: ProColumns<DomesticBatch>[] = settings.keys.flatMap((key) => {
    const field = domesticColumns.find((item) => item.key === key);
    if (!field) return [];
    return [{
      key, dataIndex: key, width: settings.widths[key] ?? field.width,
      title: <ResizableColumnTitle label={field.title} minWidth={90} width={settings.widths[key] ?? field.width}
        onWidthChange={(width) => onResize(key, width)} />,
      onHeaderCell: () => ({ className: "report-table-resizable-header-cell" }),
      fixed: key === "arrival" ? "left" as const : undefined,
      ellipsis: true,
      sorter: key === "arrival",
      sortOrder: key === "arrival" ? (sort === "received_date_desc" ? "descend" as const : sort === "received_date_asc" ? "ascend" as const : null) : undefined,
      render: (_, row) => renderCell(key, row),
    }];
  });
  columns.push({ key: "actions", title: "操作", width: 72, fixed: "right",
    render: (_, row) => <Button type="link" size="small" onClick={() => onDetail(row.id)}>详情</Button> });
  return (
    <ReportTableShell label="国内仓批次表格">
      <ProTable<DomesticBatch> rowKey="id" search={false} options={false} toolBarRender={false}
        tableAlertRender={false} bordered size="small" columns={columns} dataSource={rows} loading={loading}
        scroll={{ x: columns.reduce((sum, column) => sum + Number(column.width ?? 120), 0), y: "100%" }}
        locale={{ emptyText: <EmptyState compact title="暂无收货批次" description="当前筛选下没有数据；到仓日期以收货单实际收货日期为准。" /> }}
        onChange={(_, __, sorter, extra) => {
          if (extra.action !== "sort" || Array.isArray(sorter)) return;
          onSort(sorter.order === "ascend" ? "received_date_asc" : "received_date_desc");
        }}
        pagination={{
          current: pagination.page, pageSize: pagination.pageSize, total,
          showSizeChanger: true, showQuickJumper: true, pageSizeOptions: [20, 50, 100, 200],
          showTotal: (count) => `共 ${count.toLocaleString()} 条收货明细`,
          onChange: (page, size) => onPagination(size !== pagination.pageSize ? 1 : page, size),
        }} />
    </ReportTableShell>
  );
}
