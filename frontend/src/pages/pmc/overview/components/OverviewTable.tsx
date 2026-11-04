/** ItemID main table: ReportTableShell + ProTable, server-side paging / whitelist sort, configurable columns. */
import { ProTable } from "@ant-design/pro-components";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import EmptyState from "@/shared/states/EmptyState";
import {
  fieldMeta,
  fixedOverviewColumnKeys,
  minWidthOf,
  overviewCellRenderers,
  overviewDefaultColumnWidths,
  sortKeyOf,
  type OverviewColumn,
} from "@/pages/pmc/overview/overviewColumns";
import { fmt } from "@/pages/pmc/overview/overviewDisplay";
import type { OverviewItemRow, OverviewSort } from "@/pages/pmc/overview/overviewTypes";

interface OverviewTableProps {
  rows: OverviewItemRow[];
  total: number;
  loading: boolean;
  salesMinDays: number;
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
  sort: OverviewSort;
  currentPage: number;
  pageSize: number;
  emptyTitle: string;
  emptyText: string;
  onColumnWidthChange: (key: string, width: number) => void;
  onSortChange: (sort: OverviewSort) => void;
  onPageChange: (page: number, pageSize: number) => void;
  onOpenDetail: (row: OverviewItemRow) => void;
}

function OverviewTable({
  rows,
  total,
  loading,
  salesMinDays,
  appliedColumnKeys,
  columnWidths,
  sort,
  currentPage,
  pageSize,
  emptyTitle,
  emptyText,
  onColumnWidthChange,
  onSortChange,
  onPageChange,
  onOpenDetail,
}: OverviewTableProps) {
  const render = overviewCellRenderers(salesMinDays);
  const width = (key: string) => columnWidths[key] ?? overviewDefaultColumnWidths[key] ?? 112;
  const headerCell = () => ({ className: "report-table-resizable-header-cell" });

  const columns: OverviewColumn[] = appliedColumnKeys.flatMap((key) => {
    const field = fieldMeta(key);
    const cell = render[key];
    if (!field || !cell) return [];
    const sortBy = field.sortBy;
    return [{
      key,
      title: (
        <ResizableColumnTitle
          label={field.title}
          minWidth={minWidthOf(key)}
          width={width(key)}
          onWidthChange={(next) => onColumnWidthChange(key, next)}
        />
      ),
      width: width(key),
      align: field.align,
      fixed: fixedOverviewColumnKeys.includes(key) ? "left" : undefined,
      onHeaderCell: headerCell,
      sorter: Boolean(sortBy),
      sortOrder: sortBy && sort.by === sortBy ? (sort.order === "asc" ? "ascend" : "descend") : null,
      render: (_, row) => cell(row),
    } satisfies OverviewColumn];
  });
  const scrollX = columns.reduce((sum, column) => sum + Number(column.width ?? 112), 0);

  return (
    <ReportTableShell label="ItemID 主表" className="pmc-overview__table-shell">
      <ProTable<OverviewItemRow>
        rowKey="item_id"
        search={false}
        options={false}
        dataSource={rows}
        columns={columns}
        loading={loading}
        tableAlertRender={false}
        toolBarRender={false}
        bordered
        size="small"
        scroll={{ x: scrollX, y: "100%" }}
        rowClassName={(row) => (row.oos || row.risk ? "pmc-overview__row-risk" : "pmc-overview__row")}
        onRow={(row) => ({ onClick: () => onOpenDetail(row) })}
        onChange={(_, __, sorter, extra) => {
          if (extra.action !== "sort") return;
          const s = Array.isArray(sorter) ? sorter[0] : sorter;
          const by = s?.order ? sortKeyOf(String(s.columnKey)) : undefined;
          onSortChange(by ? { by, order: s.order === "ascend" ? "asc" : "desc" } : { order: "desc" });
        }}
        locale={{ emptyText: <EmptyState title={emptyTitle} description={emptyText} compact /> }}
        pagination={{
          current: currentPage,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
          showTotal: (count) => `共 ${fmt(count)} 个 ItemID`,
          onChange: (page, nextPageSize) => onPageChange(nextPageSize !== pageSize ? 1 : page, nextPageSize),
        }}
      />
    </ReportTableShell>
  );
}

export default OverviewTable;
