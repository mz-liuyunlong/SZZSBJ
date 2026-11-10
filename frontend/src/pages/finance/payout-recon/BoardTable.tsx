/** 本组表格：公共表格外框 + ProTable（带边框、小尺寸、表头固定）；有 resizeKey 就能拖表头调列宽，宽度记在本机（同日记账）。 */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import type { TableRowSelection } from "antd/es/table/interface";
import { Table } from "antd";
import { useState, type ReactNode } from "react";
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

function BoardTable<T extends object>({ label, rowKey, rows, columns, pageSize = 50, emptyTitle, emptyText, onRow, resizeKey, autoHeight, rowSelection, totals }: {
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
}) {
  const shown = useColumnWidths(resizeKey, columns);
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
        pagination={{ defaultPageSize: pageSize, showSizeChanger: true, showQuickJumper: true, showTotal: (count) => `共 ${count.toLocaleString()} 条` }}
        locale={{ emptyText: <EmptyState title={emptyTitle} description={emptyText} compact /> }}
      />
    </ReportTableShell>
  );
}

export default BoardTable;
