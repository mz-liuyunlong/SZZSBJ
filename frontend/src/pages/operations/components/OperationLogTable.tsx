import { ProTable, type ProColumns } from "@ant-design/pro-components";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { Button, Empty, Input, Popover, Space, Tag } from "antd";
import { useState, type Key, type ReactNode } from "react";
import { ProductIdentityCell, SkuMskuIdentityCell } from "@/components/report-table/cells";
import { MoneyCell } from "@/components/report-table/cells";
import {
  operationLogColumnFields,
  type OperationLogRow,
  type OperationLogStatus,
  type OperationLogSystemRecord,
} from "@/pages/operations/operationLogTypes";

interface OperationLogTableProps {
  rows: OperationLogRow[];
  total?: number;
  loading?: boolean;
  systemRecords: OperationLogSystemRecord[];
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
  currentPage: number;
  pageSize: number;
  selectedRowKeys: Key[];
  onColumnWidthChange: (key: string, width: number) => void;
  onCurrentPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectionChange: (keys: Key[]) => void;
  onCopy: (text: string) => void;
  onOpenProduct: (row: OperationLogRow) => void;
  onOpenEntryEditor: (row: OperationLogRow, type: "keyword" | "ad") => void;
  onManualLogChange: (rowId: string, value: string) => void;
  onSaveRow: (row: OperationLogRow) => void;
  onViewEntries: (row: OperationLogRow) => void;
  onBulkSaveDraft: () => void;
  onSubmitAll: () => void;
  tableActions?: ReactNode;
}

interface OperationLogColumn {
  key: string;
  title: string;
  width: number;
  className?: string;
  render: (row: OperationLogRow, index: number) => ReactNode;
}

const statusColor: Record<OperationLogStatus, string> = {
  待提交: "success",
  草稿: "default",
  已保存: "blue",
  缺记录: "error",
};

const systemLogPopover = (records: OperationLogSystemRecord[]) => (
  <div className="operation-log__system-popover">
    {records.length === 0 ? (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="暂无系统运营日志"
      />
    ) : (
      <div style={{
        whiteSpace: "pre-wrap",
        overflowWrap: "anywhere",
        lineHeight: 1.9,
      }}>
        {[...records]
          .sort((a, b) =>
            a.id.localeCompare(b.id, undefined, { numeric: true })
          )
          .map((record) => record.detail)
          .join("\n")}
      </div>
    )}
  </div>
);

function ManualLogEditor({
  row,
  onChange,
}: {
  row: OperationLogRow;
  onChange: (rowId: string, value: string) => void;
}) {
  const [editing, setEditing] = useState(false);

  if (!editing) {
    return (
      <Button
        type="text"
        block
        onClick={() => setEditing(true)}
        style={{
          height: "auto",
          minHeight: 40,
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
          textAlign: "left",
        }}
      >
        {row.manualLog || "点击填写日志"}
      </Button>
    );
  }

  return (
    <Input.TextArea
      autoFocus
      aria-label={`运营日志：${row.productId}`}
      value={row.manualLog}
      autoSize={{ minRows: 2, maxRows: 4 }}
      onChange={(event) => onChange(row.id, event.target.value)}
      onBlur={() => setEditing(false)}
    />
  );
}

function OperationLogTable({
  rows,
  total = rows.length,
  loading = false,
  systemRecords,
  appliedColumnKeys,
  columnWidths,
  currentPage,
  pageSize,
  selectedRowKeys,
  onColumnWidthChange,
  onCurrentPageChange,
  onPageSizeChange,
  onSelectionChange,
  onCopy,
  onManualLogChange,
  onSaveRow,
  onViewEntries,
  onBulkSaveDraft,
  onSubmitAll,
  tableActions,
}: OperationLogTableProps) {
  const columnTitleMap = new Map(operationLogColumnFields.map((field) => [field.key, field.title]));

  const allColumns: OperationLogColumn[] = [
    {
      key: "index",
      title: "#",
      width: 46,
      className: "operation-log__col-index",
      render: (_, index) => index + 1,
    },
    {
      key: "date",
      title: "日期",
      width: 108,
      render: (row) => row.date,
    },
    {
      key: "productIdShortcut",
      title: "商品ID/品名",
      width: 188,
      className: "report-table-product-identity-column",
      render: (row) => (
        <ProductIdentityCell
          productId={row.productId}
          productName={row.productName}
          onCopy={onCopy}
        />
      ),
    },
    {
      key: "skuMsku",
      title: "SKU/MSKU",
      width: 188,
      className: "report-table-sku-msku-identity-column",
      render: (row) => (
        <SkuMskuIdentityCell
          sku={row.sku}
          msku={row.msku}
          onCopy={onCopy}
        />
      ),
    },
    {
      key: "store",
      title: "店铺",
      width: 104,
      render: (row) => row.store,
    },
    {
      key: "owner",
      title: "负责人",
      width: 90,
      render: (row) => row.owner,
    },
    {
      key: "workType",
      title: "工作类型",
      width: 126,
      render: (row) => <Tag color="purple">{row.workType}</Tag>,
    },
    {
      key: "profit7d",
      title: "近7天利润",
      width: 120,
      render: (row) => (
        <MoneyCell value={row.profit7d} tone="profit" />
      ),
    },
    {
      key: "wfsAvailableInventory",
      title: "WFS可售库存",
      width: 130,
      render: (row) => (
        row.wfsAvailableInventory == null
          ? "—"
          : row.wfsAvailableInventory.toLocaleString("en-US", {
              maximumFractionDigits: 4,
            })
      ),
    },
    {
      key: "systemLogs",
      title: "系统日志",
      width: 104,
      render: (row) => {
        const records = systemRecords.filter((record) => record.productId === row.productId && record.storeId === row.storeId && record.sourceAccountRef === row.sourceAccountRef && record.date === row.date && record.msku === row.msku);
        return (
          <Popover content={systemLogPopover(records)} title={`${row.productId} 系统日志`} trigger="hover">
            <Tag className="operation-log__system-tag" color={records.length ? "green" : "red"}>
              {records.length ? `系统${records.length}条` : "系统缺"}
            </Tag>
          </Popover>
        );
      },
    },
    {
      key: "manualLog",
      title: "运营日志，可直接填写",
      width: 360,
      className: "operation-log__col-manual-log",
      render: (row) => (
        <ManualLogEditor
          row={
            row.manualLog.trim()
              ? row
              : { ...row, manualLog: row.legacyManualLog ?? "" }
          }
          onChange={onManualLogChange}
        />
      ),
    },
    {
      key: "status",
      title: "状态",
      width: 88,
      render: (row) => (
        <Tag color={statusColor[row.status]}>{row.status}</Tag>
      ),
    },
    {
      key: "actions",
      title: "操作",
      width: 86,
      render: (row) => <Space size={4}><Button onClick={() => onSaveRow(row)}>保存</Button><Button type="link" onClick={() => onViewEntries(row)}>查看全部{row.manualEntryCount ? ` (${row.manualEntryCount})` : ""}</Button></Space>,
    },
  ];

  const columns = allColumns.filter((column) => column.key === "skuMsku" || appliedColumnKeys.includes(column.key));


  // PROTABLE_OPERATION_LOGS_20261021
  const visibleColumns: ProColumns<OperationLogRow>[] =
    columns.map((column) => {
      const width = columnWidths[column.key] ?? column.width;

      return {
        key: column.key,
        className: column.className,
        width,
        align: "left" as const,
        title: (
          <ResizableColumnTitle
            label={columnTitleMap.get(column.key) ?? column.title}
            width={width}
            minWidth={80}
            onWidthChange={(nextWidth) =>
              onColumnWidthChange(column.key, nextWidth)
            }
          />
        ),
        render: (_value, row, index) => column.render(row, index),
      };
    });

  return (
    <ReportTableShell
      className="operation-log__table"
      label="商品ID维度运营日志表"
    >
      <div className="operation-log__table-head">
        <div>
          <strong>商品ID维度运营日志</strong>
          <span> · 按登录用户权限查询，服务端分页</span>
        </div>
        {tableActions ? (
          <div className="operation-log__table-actions">
            {tableActions}
          </div>
        ) : null}
      </div>

      <ProTable<OperationLogRow>
        rowKey="id"
        columns={visibleColumns}
        dataSource={rows}
        loading={loading}
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        tableAlertOptionRender={false}
        rowSelection={{
          fixed: true,
          selectedRowKeys,
          onChange: onSelectionChange,
        }}
        scroll={{ x: "max-content" }}
        pagination={{
          current: currentPage,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: ["50", "100"],
          showTotal: (count) => `共 ${count} 条`,
          onChange: (nextPage, nextSize) => {
            if (nextSize !== pageSize) {
              onPageSizeChange(nextSize);
            } else {
              onCurrentPageChange(nextPage);
            }
          },
        }}
        locale={{
          emptyText: <Empty description="暂无匹配运营日志" />,
        }}
      />

      <div className="operation-log__sticky-foot">
        <span>
          当前页 {rows.length} 条，共 {total} 条。
          批量写入仅处理当前页商品。
        </span>
        <Space>
          <Button onClick={onBulkSaveDraft}>
            保存当前页草稿
          </Button>
          <Button type="primary" onClick={onSubmitAll}>
            提交当前页
          </Button>
        </Space>
      </div>
    </ReportTableShell>
  );

}

export default OperationLogTable;
