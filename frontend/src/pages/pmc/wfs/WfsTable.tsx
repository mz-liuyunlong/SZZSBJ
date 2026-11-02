/** ProTable frame used by every WFS preview page. */
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import type { TableRowSelection } from "antd/es/table/interface";
import ReportTableShell from "@/components/report-table/ReportTableShell";

const pagination = { pageSize: 20, showSizeChanger: false };

export default function WfsTable<T extends { id: string }>({
  label,
  columns,
  rows,
  rowSelection,
}: {
  label: string;
  columns: ProColumns<T>[];
  rows: T[];
  rowSelection?: TableRowSelection<T>;
}) {
  return (
    <ReportTableShell label={label}>
      <ProTable<T>
        rowKey="id"
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        size="small"
        bordered
        columns={columns}
        dataSource={rows}
        rowSelection={rowSelection}
        pagination={pagination}
        scroll={{ x: "max-content" }}
      />
    </ReportTableShell>
  );
}
