import { Button, Empty, Input, Popover, Space, Tag } from "antd";
import type { Key, ReactNode } from "react";
import {
  operationLogColumnFields,
  type OperationLogRow,
  type OperationLogStatus,
  type OperationLogSystemRecord,
} from "@/pages/operations/operationLogTypes";

interface OperationLogTableProps {
  rows: OperationLogRow[];
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
  onManualLogChange: (productId: string, value: string) => void;
  onSaveRow: (row: OperationLogRow) => void;
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
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有抓到系统广告调整记录" />
    ) : records.map((record) => (
      <div className="operation-log__system-card" key={record.id}>
        <div>
          <Tag color="blue">{record.time}</Tag>
          <strong>{record.type}</strong>
          <span>{record.owner} · {record.source}</span>
        </div>
        <p>{record.object}：{record.before} → {record.after}</p>
        <small>{record.detail}</small>
      </div>
    ))}
  </div>
);

function ShortcutButton({
  label,
  missing,
  onClick,
}: {
  label: string;
  missing: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`operation-log__mini-icon${missing ? " operation-log__mini-icon--missing" : ""}`}
      onClick={onClick}
      title={missing ? `${label}页面缺失，点击补录` : `打开${label}页面`}
    >
      {label}
    </button>
  );
}

function OperationLogTable({
  rows,
  systemRecords,
  appliedColumnKeys,
  columnWidths,
  onOpenProduct,
  onOpenEntryEditor,
  onManualLogChange,
  onSaveRow,
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
      title: "商品ID / 快捷入口",
      width: 248,
      className: "operation-log__col-product",
      render: (row) => {
        const keywordMissing = row.keywordEntryStatus === "missing";
        const adMissing = row.adEntryStatus === "missing";

        return (
          <div className="operation-log__pid-cell">
            <div className="operation-log__pid-main">
              <button
                type="button"
                className="operation-log__pid-link"
                onClick={() => onOpenProduct(row)}
              >
                {row.productId}
              </button>
              <span>{row.sku} · {row.store}</span>
            </div>
            <div className="operation-log__mini-icons">
              <ShortcutButton
                label="词"
                missing={keywordMissing}
                onClick={() => onOpenEntryEditor(row, "keyword")}
              />
              <ShortcutButton
                label="广"
                missing={adMissing}
                onClick={() => onOpenEntryEditor(row, "ad")}
              />
            </div>
          </div>
        );
      },
    },
    {
      key: "productName",
      title: "商品名称",
      width: 176,
      render: (row) => row.productName,
    },
    {
      key: "store",
      title: "店铺",
      width: 104,
      render: (row) => row.store,
    },
    {
      key: "owner",
      title: "运营",
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
      key: "conversionRate",
      title: "转化率",
      width: 86,
      render: (row) => `${row.conversionRate.toFixed(1)}%`,
    },
    {
      key: "adRatio",
      title: "广告占比",
      width: 92,
      render: (row) => (row.adRatio === undefined ? "-" : `${row.adRatio.toFixed(1)}%`),
    },
    {
      key: "salePrice",
      title: "销售价",
      width: 92,
      render: (row) => `$${row.salePrice.toFixed(2)}`,
    },
    {
      key: "systemLogs",
      title: "系统日志",
      width: 104,
      render: (row) => {
        const records = systemRecords.filter((record) => record.productId === row.productId);
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
        <Input.TextArea
          aria-label={`运营日志：${row.productId}`}
          value={row.manualLog}
          rows={2}
          autoSize={{ minRows: 2, maxRows: 3 }}
          onChange={(event) => onManualLogChange(row.productId, event.target.value)}
        />
      ),
    },
    {
      key: "status",
      title: "状态",
      width: 88,
      render: (row) => <Tag color={statusColor[row.status]}>{row.status}</Tag>,
    },
    {
      key: "actions",
      title: "操作",
      width: 86,
      render: (row) => <Button onClick={() => onSaveRow(row)}>保存</Button>,
    },
  ];

  const columns = allColumns.filter((column) => appliedColumnKeys.includes(column.key));

  return (
    <section className="operation-log__table" aria-label="商品ID维度运营日志表">
      <div className="operation-log__table-head">
        <div>
          <strong>商品ID维度运营日志</strong>
          <span> · 表格内单行编辑；批量写入在弹窗内选择商品ID；鼠标移入系统日志查看详情</span>
        </div>
        {tableActions ? <div className="operation-log__table-actions">{tableActions}</div> : null}
      </div>

      <div className="operation-log__native-table-wrap">
        <table className="operation-log__native-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  className={column.className}
                  style={{ minWidth: columnWidths[column.key] ?? column.width }}
                >
                  {columnTitleMap.get(column.key) ?? column.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length}>
                  <div className="operation-log__empty">暂无运营日志</div>
                </td>
              </tr>
            ) : rows.map((row, index) => (
              <tr key={row.id}>
                {columns.map((column) => (
                  <td
                    key={`${row.id}-${column.key}`}
                    className={column.className}
                    style={{ minWidth: columnWidths[column.key] ?? column.width }}
                  >
                    {column.render(row, index)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="operation-log__sticky-foot">
        <span>
          批量写入不依赖外部表格勾选；请在弹窗内搜索并选择商品ID。词/广缺失时点击红色入口即可补录。
        </span>
        <Space>
          <Button onClick={onBulkSaveDraft}>保存草稿</Button>
          <Button type="primary" onClick={onSubmitAll}>提交全部</Button>
        </Space>
      </div>
    </section>
  );
}

export default OperationLogTable;
