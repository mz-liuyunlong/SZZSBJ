/** 资金流水页面共用的表格壳；从 FinanceCashFlowPage.tsx 原样搬出。 */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import type { ExpandableConfig, TableRowSelection } from "antd/es/table/interface";
import { useState } from "react";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { readUserPreference, writeUserPreference } from "@/shared/preferences/userPreferenceCache";
import EmptyState from "@/shared/states/EmptyState";
import { scrollX } from "@/pages/finance/cash-flow/journalShared";

const WIDTH_PREF_VERSION = 1;
const MIN_WIDTH = 64;
const headerCell = () => ({ className: "report-table-resizable-header-cell" });

/** 有 resizeKey 就让表头可以拖动调列宽（和 PMC 各表同一个拖动控件），调完的宽度记在本机偏好里。 */
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

export function BoardTable<T extends object>({ label, rowKey, rows, columns, emptyTitle, emptyText, pageSize = 50, rowSelection, resizeKey, expandable }: {
  label: string; rowKey: string | ((row: T) => string); rows: T[]; columns: ProColumns<T>[]; emptyTitle: string; emptyText: string; pageSize?: number;
  /** 有就在最左边加勾选列（日记账批量操作用） */
  rowSelection?: TableRowSelection<T>;
  /** 有就可以拖表头调列宽，宽度按这个键记住 */
  resizeKey?: string;
  /** 树形子行（日记账拆分行）的展开控制 */
  expandable?: ExpandableConfig<T>;
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
        columns={shown}
        rowSelection={rowSelection}
        expandable={expandable}
        scroll={{ x: scrollX(shown) + (rowSelection ? Number(rowSelection.columnWidth ?? 48) : 0), y: "100%" }}
        locale={{ emptyText: <EmptyState title={emptyTitle} description={emptyText} compact /> }}
        pagination={{ defaultPageSize: pageSize, showSizeChanger: true, showQuickJumper: true, showTotal: (count) => `共 ${count.toLocaleString()} 条` }}
      />
    </ReportTableShell>
  );
}
