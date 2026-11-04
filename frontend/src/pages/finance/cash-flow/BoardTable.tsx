/** 资金流水页面共用的表格壳；从 FinanceCashFlowPage.tsx 原样搬出。 */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import EmptyState from "@/shared/states/EmptyState";
import { scrollX } from "@/pages/finance/cash-flow/journalShared";

export function BoardTable<T extends object>({ label, rowKey, rows, columns, emptyTitle, emptyText, pageSize = 50 }: {
  label: string; rowKey: string | ((row: T) => string); rows: T[]; columns: ProColumns<T>[]; emptyTitle: string; emptyText: string; pageSize?: number;
}) {
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
        columns={columns}
        scroll={{ x: scrollX(columns), y: "100%" }}
        locale={{ emptyText: <EmptyState title={emptyTitle} description={emptyText} compact /> }}
        pagination={{ defaultPageSize: pageSize, showSizeChanger: true, showQuickJumper: true, showTotal: (count) => `共 ${count.toLocaleString()} 条` }}
      />
    </ReportTableShell>
  );
}
