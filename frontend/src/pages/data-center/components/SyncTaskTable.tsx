import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Space, Switch, Tooltip, Typography } from "antd";
import type { Key } from "react";
import { StatusTagCell } from "@/components/report-table/cells";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import type { SyncTaskRow, SyncTaskStatus } from "@/pages/data-center/syncTaskTypes";

interface SyncTaskTableProps {
  rows: SyncTaskRow[];
  columnWidths: Record<string, number>;
  selectedRowKeys: Key[];
  currentPage: number;
  pageSize: number;
  onCurrentPageChange: (page: number) => void;
  onColumnWidthChange: (key: string, width: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectionChange: (keys: Key[]) => void;
  onOpenConfig: (task: SyncTaskRow) => void;
  onOpenLog: (task: SyncTaskRow) => void;
  onRequestSync: (task: SyncTaskRow) => void;
  onRequestRetry: (task: SyncTaskRow) => void;
  onToggleAutoSync: (task: SyncTaskRow, checked: boolean) => void;
  onBulkAction: () => void;
}

const statusColors: Record<SyncTaskStatus, string> = {
  成功: "success",
  失败: "error",
  运行中: "processing",
  部分成功: "warning",
  超时: "orange",
  已停用: "default",
};

const anomalyStatuses = new Set<SyncTaskStatus>(["失败", "超时", "部分成功"]);

const compareText = (left: string, right: string) => left.localeCompare(right, "zh-CN");
const compareDate = (left?: string, right?: string) => Date.parse(left ?? "") - Date.parse(right ?? "");

function SyncTaskTable({
  rows,
  columnWidths,
  selectedRowKeys,
  currentPage,
  pageSize,
  onCurrentPageChange,
  onColumnWidthChange,
  onPageSizeChange,
  onSelectionChange,
  onOpenConfig,
  onOpenLog,
  onRequestSync,
  onRequestRetry,
  onToggleAutoSync,
  onBulkAction,
}: SyncTaskTableProps) {
  const baseColumns: ProColumns<SyncTaskRow>[] = [
    {
      title: "任务名称",
      dataIndex: "taskName",
      key: "taskName",
      width: 190,
      fixed: "left",
      sorter: (left, right) => compareText(left.taskName, right.taskName),
      render: (_, row) => (
        <Tooltip title={row.interfaceName}>
          <Button type="link" className="sync-task__task-name" onClick={() => onOpenConfig(row)}>
            {row.taskName}
          </Button>
        </Tooltip>
      ),
    },
    {
      title: "模块",
      dataIndex: "module",
      key: "module",
      width: 86,
      sorter: (left, right) => compareText(left.module, right.module),
    },
    {
      title: "自动同步",
      dataIndex: "autoSync",
      key: "autoSync",
      width: 94,
      render: (_, row) => (
        <Switch
          size="small"
          checked={row.autoSync}
          aria-label={`${row.taskName}自动同步开关`}
          onChange={(checked) => onToggleAutoSync(row, checked)}
        />
      ),
    },
    {
      title: "同步频率",
      dataIndex: "frequency",
      key: "frequency",
      width: 120,
    },
    {
      title: "下次同步时间",
      dataIndex: "nextRunAt",
      key: "nextRunAt",
      width: 158,
      sorter: (left, right) => compareDate(left.nextRunAt, right.nextRunAt),
      render: (_, row) => row.nextRunAt ?? <Typography.Text type="secondary">-</Typography.Text>,
    },
    {
      title: "最近状态",
      dataIndex: "lastStatus",
      key: "lastStatus",
      width: 124,
      render: (_, row) => <StatusTagCell label={row.lastStatus} color={statusColors[row.lastStatus]} />,
    },
    {
      title: "最近同步时间",
      dataIndex: "lastRunAt",
      key: "lastRunAt",
      width: 158,
      sorter: (left, right) => compareDate(left.lastRunAt, right.lastRunAt),
    },
    {
      title: "今日成功/失败",
      key: "todayResult",
      width: 124,
      sorter: (left, right) => (left.todaySuccess + left.todayFailed) - (right.todaySuccess + right.todayFailed),
      render: (_, row) => `${row.todaySuccess} / ${row.todayFailed}`,
    },
    {
      title: "操作",
      key: "actions",
      width: 178,
      fixed: "right",
      render: (_, row) => {
        const primaryAction = anomalyStatuses.has(row.lastStatus) ? (
          <Button type="link" danger onClick={() => onRequestRetry(row)}>重试</Button>
        ) : row.lastStatus === "运行中" ? (
          <Tooltip title="任务运行中，不可重复触发">
            <Button type="link" disabled>立即同步</Button>
          </Tooltip>
        ) : (
          <Button type="link" onClick={() => onRequestSync(row)}>立即同步</Button>
        );

        return (
          <Space size={4} className="sync-task__row-actions">
            {primaryAction}
            <Button type="link" onClick={() => onOpenConfig(row)}>配置</Button>
            <Button type="link" onClick={() => onOpenLog(row)}>日志</Button>
          </Space>
        );
      },
    },
  ];
  const columns = baseColumns.map((column) => {
    const key = String(column.key);
    const label = String(column.title);
    const width = columnWidths[key] ?? (Number(column.width) || 112);
    const minWidth = Math.max(key === "actions" ? 160 : 88, label.length * 14 + 28);

    return {
      ...column,
      width,
      onHeaderCell: () => ({ className: "report-table-resizable-header-cell" }),
      title: (
        <ResizableColumnTitle
          label={label}
          minWidth={minWidth}
          width={width}
          onWidthChange={(nextWidth) => onColumnWidthChange(key, nextWidth)}
        />
      ),
    };
  });

  return (
    <ReportTableShell className="sync-task__table-shell" label="同步任务总控表格">
      <ProTable<SyncTaskRow>
        columns={columns}
        dataSource={rows}
        rowKey="id"
        rowSelection={{ fixed: true, selectedRowKeys, onChange: onSelectionChange }}
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        tableAlertOptionRender={false}
        showSorterTooltip={{ target: "sorter-icon" }}
        rowClassName={(row) => `sync-task__row sync-task__row--${row.lastStatus}`}
        scroll={{ x: "max-content", y: "max(260px, calc(100dvh - 390px))" }}
        footer={() => (
          <div className="sync-task__selection-footer">
            <Space>
              <Typography.Text type="secondary">已选择 {selectedRowKeys.length} 项</Typography.Text>
              <Button disabled={selectedRowKeys.length === 0} onClick={onBulkAction}>批量操作</Button>
            </Space>
          </div>
        )}
        pagination={{
          current: currentPage,
          pageSize,
          total: rows.length,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (nextPage, nextPageSize) => {
            if (nextPageSize !== pageSize) {
              onPageSizeChange(nextPageSize);
              return;
            }
            onCurrentPageChange(nextPage);
          },
        }}
        locale={{
          emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配同步任务" />,
        }}
      />
    </ReportTableShell>
  );
}

export default SyncTaskTable;
