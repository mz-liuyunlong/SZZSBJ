/** Small read-only ProTable used inside the 总看板 drawer and tabs (no toolbar, no paging). */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import EmptyState from "@/shared/states/EmptyState";

interface OverviewDetailTableProps<T extends Record<string, unknown>> {
  label: string;
  rowKey: string | ((row: T) => string);
  rows: T[];
  columns: ProColumns<T>[];
  loading?: boolean;
  emptyText?: string;
  rowClassName?: (row: T) => string;
}

function OverviewDetailTable<T extends Record<string, unknown>>({
  label, rowKey, rows, columns, loading, emptyText = "暂无记录", rowClassName,
}: OverviewDetailTableProps<T>) {
  return (
    <ProTable<T>
      aria-label={label}
      rowKey={rowKey}
      search={false}
      options={false}
      toolBarRender={false}
      tableAlertRender={false}
      size="small"
      bordered
      loading={loading}
      dataSource={rows}
      columns={columns}
      pagination={false}
      rowClassName={rowClassName}
      locale={{ emptyText: <EmptyState title="暂无数据" description={emptyText} compact /> }}
    />
  );
}

export default OverviewDetailTable;
