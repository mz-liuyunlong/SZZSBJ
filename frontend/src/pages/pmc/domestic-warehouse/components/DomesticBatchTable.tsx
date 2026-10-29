import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Space, Tag, Tooltip } from "antd";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { CopyableTextCell } from "@/components/report-table/cells";
import EmptyState from "@/shared/states/EmptyState";
import { arrivalSourceText, domesticColumns, formatQuantity, type BatchSort, type DomesticBatch } from "../domesticWarehouseTypes";

interface Props {
  rows: DomesticBatch[]; total: number; emptyTitle: string; emptyDescription: string;
  columns: { keys: string[]; widths: Record<string, number> }; pagination: { page: number; pageSize: number }; sort: BatchSort;
  onPagination: (page: number, size: number) => void; onSort: (sort: BatchSort) => void;
  onResize: (key: string, width: number) => void; onDetail: (id: string) => void;
}
function copyStack(values: string[] | undefined, label: string) {
  const items = (values ?? []).map((value) => value.trim()).filter(Boolean);
  if (!items.length) return "—";
  if (items.length === 1) return <CopyableTextCell text={items[0]} label={label} />;
  return (
    <Space direction="vertical" size={0} className="report-table-identity-stack">
      {items.map((value) => <CopyableTextCell key={value} text={value} label={label} />)}
    </Space>
  );
}
function renderCell(key: string, row: DomesticBatch) {
  switch (key) {
    case "arrival": return row.arrival_business_date ? <Tooltip title={`来源：${arrivalSourceText[row.arrival_source]}；原值：${row.inbound_at_raw ?? "未知"}`}>{row.arrival_business_date}</Tooltip> : <Tag color="warning">待核实</Tag>;
    case "draft": return copyStack(row.draft_nos, "草稿号");
    case "inbound":
      return row.inbound_order_sn.trim()
        ? <CopyableTextCell text={row.inbound_order_sn} label="入库单号" />
        : "—";
    case "purchase": {
      const purchaseOrders = row.purchase_order_sns.map((sn) => sn.trim()).filter(Boolean);
      if (!purchaseOrders.length) return "—";
      if (purchaseOrders.length === 1) {
        return <CopyableTextCell text={purchaseOrders[0]} label="采购单号" />;
      }
      return (
        <Space direction="vertical" size={0} className="report-table-identity-stack">
          {purchaseOrders.map((sn) => (
            <CopyableTextCell key={sn} text={sn} label="采购单号" />
          ))}
        </Space>
      );
    }
    case "sku":
      return row.sku.trim()
        ? <CopyableTextCell text={row.sku} label="SKU" />
        : "—";
    case "product": return row.product_name || "—";
    case "store": return row.store_id ? `${row.store_name || "店铺"} (${row.store_id})` : <Tag>归属未知</Tag>;
    case "item": return <Space direction="vertical" size={0}>
      {row.item_identities?.length
        ? row.item_identities.map((identity, index) => <CopyableTextCell key={`${identity.item_id}:${index}`} text={identity.item_id} label="ItemID" />)
        : <Tooltip title="这家店的备注和 Listing 都没有对上 ItemID"><Tag>待归属</Tag></Tooltip>}
      {row.identity_status === "conflict" && <Tag color="warning">归属冲突</Tag>}
      {row.identity_status === "partial" && <Tag color="warning">归属不完整</Tag>}
      {row.identity_status === "multiple" && <Tag color="warning">多 listing（{row.item_identities?.length ?? 0}）</Tag>}
    </Space>;
    case "gtin": return row.item_identities?.length ? <Space direction="vertical" size={0}>
      {row.item_identities.map((identity, index) => <Tooltip key={`${identity.item_id}:${index}`} title={`对应 ItemID：${identity.item_id}`}>
        <span>{identity.gtin ? <CopyableTextCell text={identity.gtin} label="GTIN" /> : <Tag>待补齐</Tag>}</span>
      </Tooltip>)}
    </Space> : <Tooltip title="商品归属确定后展示对应 GTIN"><Tag>待补齐</Tag></Tooltip>;
    case "owner": return row.owner?.status === "conflict" ? <Tag color="warning">负责人冲突</Tag>
      : row.owner?.status === "resolved" && (row.owner.name?.trim() || row.owner.uid?.trim())
        ? <Tooltip title="当前产品负责人">{row.owner.name?.trim() || row.owner.uid}</Tooltip>
        : <Tooltip title="当前产品资料没有这个 SKU 的唯一负责人"><Tag>未知</Tag></Tooltip>;
    case "age": return row.days_in_warehouse === null ? "—" : `${row.days_in_warehouse} 天`;
    case "quantity": return <Tooltip title="该数量属于整个 IB×SKU，可能在多个店铺行重复展示；请以去重统计为准，不能直接累加此列。">{formatQuantity(row.parent_inbound_qty)}</Tooltip>;
    case "balance": return formatQuantity(row.balance_num);
    case "batches": return row.batch_nos.join(" / ") || "—";
    case "warehouse": return row.warehouse_name ? `${row.warehouse_name} (${row.source_warehouse_id})` : row.source_warehouse_id;
    case "account": return row.source_account_ref;
    case "inventory": return <Tag color={row.inventory_status === "known" ? "success" : "warning"}>{row.inventory_status === "known" ? "余额已知" : "余额未知"}</Tag>;
    case "source": return <Tag>{row.source_kind === "inventory_statement" ? "库存流水" : "批次历史补充"}</Tag>;
    default: return "—";
  }
}
export default function DomesticBatchTable({ rows, total, emptyTitle, emptyDescription, columns: settings, pagination, sort, onPagination, onSort, onResize, onDetail }: Props) {
  const columns: ProColumns<DomesticBatch>[] = settings.keys.flatMap((key) => {
    const field = domesticColumns.find((v) => v.key === key);
    if (!field) return [];
    const sortOrder = key === "arrival" ? sort === "inbound_date_desc" ? "descend" : sort === "inbound_date_asc" ? "ascend" : null
      : key === "balance" && sort === "balance_desc" ? "descend" : null;
    return [{ key, dataIndex: key, width: settings.widths[key] ?? field.width,
      title: <ResizableColumnTitle label={field.title} minWidth={90} width={settings.widths[key] ?? field.width} onWidthChange={(width) => onResize(key, width)} />,
      onHeaderCell: () => ({ className: "report-table-resizable-header-cell" }), fixed: key === "arrival" ? "left" as const : undefined,
      ellipsis: true, sorter: key === "arrival" || key === "balance", sortOrder, render: (_, row) => renderCell(key, row) }];
  });
  columns.push({ key: "actions", title: "操作", width: 80, fixed: "right", render: (_, row) => <Button type="link" size="small" onClick={() => onDetail(row.id)}>核对详情</Button> });
  return <ReportTableShell label="国内仓批次表格"><ProTable<DomesticBatch> rowKey="id" search={false} options={false} toolBarRender={false}
    tableAlertRender={false} bordered size="small" columns={columns} dataSource={rows}
    scroll={{ x: columns.reduce((sum, column) => sum + Number(column.width ?? 120), 0), y: "100%" }}
    locale={{ emptyText: <EmptyState compact title={emptyTitle} description={emptyDescription} /> }}
    onChange={(_, __, sorter, extra) => {
      if (extra.action !== "sort" || Array.isArray(sorter)) return;
      onSort(sorter.columnKey === "balance" ? "balance_desc" : sorter.order === "ascend" ? "inbound_date_asc" : "inbound_date_desc");
    }} pagination={{ current: pagination.page, pageSize: pagination.pageSize, total, showSizeChanger: true, showQuickJumper: true,
      pageSizeOptions: [20, 50, 100, 200], showTotal: (count) => `共 ${count.toLocaleString()} 条入库展示行`,
      onChange: (page, size) => onPagination(size !== pagination.pageSize ? 1 : page, size) }} />
  </ReportTableShell>;
}
