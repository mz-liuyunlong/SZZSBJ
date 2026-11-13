/** 本组表格：公共表格外框 + ProTable（带边框、小尺寸、表头固定）；有 resizeKey 就能拖表头调列宽，宽度记在本机（同日记账）。 */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import type { TableRowSelection } from "antd/es/table/interface";
import { Pagination, Table } from "antd";
import { useState, type ReactNode } from "react";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";
import EmptyState from "@/shared/states/EmptyState";

const WIDTH_PREF_VERSION = 1;
const MIN_WIDTH = 64;
const headerCell = () => ({ className: "report-table-resizable-header-cell" });
const scrollX = <T,>(columns: ProColumns<T>[]) => columns.reduce((total, column) => total + Number(column.width ?? 120), 0);

function useColumnWidths<T>(resizeKey: string | undefined, columns: ProColumns<T>[]): ProColumns<T>[] {
  const prefKey = `${resizeKey}:widths`;
  const [widths, setWidths] = useState<Record<string, number>>(() => (resizeKey ? readUserPreference<Record<string, number>>("anonymous", prefKey, WIDTH_PREF_VERSION) ?? {} : {}));
  if (!resizeKey) return columns;
  const change = (key: string, width: number) => setWidths((current) => {
    const next = { ...current, [key]: width };
    writeUserPreference("anonymous", prefKey, WIDTH_PREF_VERSION, next);
    return next;
  });
  return columns.map((column) => {
    const key = String(column.key ?? "");
    if (!key || typeof column.title !== "string" || typeof column.width !== "number") return column;
    const width = widths[key] ?? column.width;
    return { ...column, width, onHeaderCell: headerCell, title: <ResizableColumnTitle label={column.title} minWidth={MIN_WIDTH} width={width} onWidthChange={(next) => change(key, next)} /> };
  });
}

function BoardTable<T extends object>({ label, rowKey, rows, columns, pageSize = 50, emptyTitle, emptyText, onRow, resizeKey, autoHeight, rowSelection, totals, serverPage }: {
  label: string;
  rowKey: string | ((row: T) => string);
  rows: T[];
  columns: ProColumns<T>[];
  pageSize?: number;
  emptyTitle: string;
  emptyText: string;
  onRow?: (row: T) => void;
  /** 有就可以拖表头调列宽，宽度按这个键记住 */
  resizeKey?: string;
  /** 放在抽屉里时不撑满高度（按行数自然高），否则表格体高度为 0、看不到行 */
  autoHeight?: boolean;
  /** 勾选列（批量操作 / 导出勾选用） */
  rowSelection?: TableRowSelection<T>;
  /** 合计行（固定在表格底部）：按列 key 给内容，没给的列留空 */
  totals?: Record<string, ReactNode>;
  /** 后端分页（行数太多、只取当前页时）：给了就用它的页码 / 总数，不在前端再切页 */
  serverPage?: { current: number; pageSize: number; total: number; onChange: (page: number, pageSize: number) => void };
}) {
  // 和 ProTable 渲染时同一个顺序：固定在左的在前、固定在右的在后（列配置里存的顺序可能把右固定列排在前面），
  // 合计行按这个顺序出格子，才不会错位
  const sized = useColumnWidths(resizeKey, columns);
  const shown = [
    ...sized.filter((c) => c.fixed === "left" || c.fixed === true),
    ...sized.filter((c) => !c.fixed),
    ...sized.filter((c) => c.fixed === "right"),
  ];
  return (
    <ReportTableShell label={label}>
      <ProTable<T>
        rowKey={rowKey}
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        bordered
        size="small"
        dataSource={rows}
        rowSelection={rowSelection}
        summary={totals ? () => (
          <Table.Summary fixed="bottom">
            <Table.Summary.Row className="fin-payout-recon__total-row">
              {rowSelection && <Table.Summary.Cell index={0} />}
              {shown.map((column, index) => (
                <Table.Summary.Cell key={String(column.key ?? index)} index={index + (rowSelection ? 1 : 0)} align={column.align}>
                  {totals[String(column.key ?? "")] ?? null}
                </Table.Summary.Cell>
              ))}
            </Table.Summary.Row>
          </Table.Summary>
        ) : undefined}
        columns={shown}
        scroll={autoHeight ? { x: scrollX(shown) } : { x: scrollX(shown), y: "100%" }}
        onRow={onRow ? (row) => ({ onDoubleClick: () => onRow(row) }) : undefined}
        // 后端分页时表格自己不切页（一页里可能有平铺的分摊行，行数比每页条数多），分页条放在表格底部（footer）里
        pagination={serverPage ? false : { defaultPageSize: pageSize, showSizeChanger: true, showQuickJumper: true, showTotal: (count) => `共 ${count.toLocaleString()} 条` }}
        footer={serverPage ? () => (
          <div className="board-table__server-pager">
            <Pagination size="small" current={serverPage.current} pageSize={serverPage.pageSize} total={serverPage.total} onChange={serverPage.onChange}
              showSizeChanger showQuickJumper pageSizeOptions={REPORT_TABLE_PAGE_SIZE_OPTIONS} showTotal={(count) => `共 ${count.toLocaleString()} 条`} />
          </div>
        ) : undefined}
        locale={{ emptyText: <EmptyState title={emptyTitle} description={emptyText} compact /> }}
      />
    </ReportTableShell>
  );
}

export default BoardTable;
