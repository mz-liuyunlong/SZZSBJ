import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Empty, Space, Table, Tag } from "antd";
import type { Key } from "react";
import ReportTableShell, { ReportTableSelectionBar } from "@/components/report-table/ReportTableShell";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import ResizableColumnTitle from "@/components/report-table/ResizableColumnTitle";
import { CopyableTextCell, MoneyCell, StatusTagCell } from "@/components/report-table/cells";
import {
  WFS_FEE_ALERT_USD_TO_CNY_RATE,
  formatWfsMoney,
  wfsFeeAlertColumnFields,
  type WfsFeeAlertCurrency,
  type WfsFeeAlertPriority,
  type WfsFeeAlertRow,
} from "@/pages/warehouse/wfsFeeAlertTypes";

interface WfsFeeAlertTableProps {
  rows: WfsFeeAlertRow[];
  currency: WfsFeeAlertCurrency;
  appliedColumnKeys: string[];
  columnWidths: Record<string, number>;
  currentPage: number;
  pageSize: number;
  selectedRowKeys: Key[];
  onColumnWidthChange: (key: string, width: number) => void;
  onCurrentPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSelectionChange: (keys: Key[]) => void;
  onBulkOpenCase: () => void;
  onBulkFollow: () => void;
  onCopy: (text: string) => void;
  onOpenDetail: (row: WfsFeeAlertRow) => void;
  onOpenFollow: (row: WfsFeeAlertRow) => void;
}

const priorityColor: Record<WfsFeeAlertPriority, string> = {
  高: "red",
  中: "orange",
  低: "default",
};

const statusColor: Record<WfsFeeAlertRow["status"], string> = {
  未开Case: "warning",
  已开Case: "processing",
  跟进中: "blue",
  已追回: "success",
  驳回: "error",
  已关闭: "default",
};

const compareText = (left: string, right: string) => left.localeCompare(right, "zh-CN");
const numberSorter = (key: keyof WfsFeeAlertRow) => (left: WfsFeeAlertRow, right: WfsFeeAlertRow) =>
  Number(left[key]) - Number(right[key]);

const moneyRender = (key: keyof WfsFeeAlertRow, currency: WfsFeeAlertCurrency) => {
  const rate = currency === "CNY" ? WFS_FEE_ALERT_USD_TO_CNY_RATE : 1;
  return (_: unknown, row: WfsFeeAlertRow) => (
    <MoneyCell value={Number(row[key]) * rate} currency={currency === "CNY" ? "¥" : "$"} />
  );
};

const createColumns = (
  currency: WfsFeeAlertCurrency,
  onCopy: (text: string) => void,
  onOpenDetail: (row: WfsFeeAlertRow) => void,
  onOpenFollow: (row: WfsFeeAlertRow) => void,
): ProColumns<WfsFeeAlertRow>[] => [
  {
    title: "图片",
    key: "image",
    width: 72,
    fixed: "left",
    render: (_, row) => (
      <span className="wfs-fee-alert__product-image" aria-label={row.imageLabel}>
        {row.imageSymbol}
      </span>
    ),
  },
  {
    title: "SKU",
    key: "sku",
    width: 154,
    fixed: "left",
    sorter: (a, b) => compareText(a.sku, b.sku),
    render: (_, row) => (
      <CopyableTextCell
        text={row.sku}
        label="SKU"
        link
        onCopy={onCopy}
        onOpen={() => onOpenDetail(row)}
      />
    ),
  },
  {
    title: "MSKU",
    dataIndex: "msku",
    key: "msku",
    width: 138,
    sorter: (a, b) => compareText(a.msku, b.msku),
  },
  {
    title: "店铺",
    dataIndex: "store",
    key: "store",
    width: 104,
    sorter: (a, b) => compareText(a.store, b.store),
  },
  {
    title: "负责人",
    dataIndex: "owner",
    key: "owner",
    width: 96,
    sorter: (a, b) => compareText(a.owner, b.owner),
  },
  {
    title: "商品ID",
    dataIndex: "productId",
    key: "productId",
    width: 128,
    sorter: (a, b) => compareText(a.productId, b.productId),
  },
  {
    title: "类目",
    dataIndex: "category",
    key: "category",
    width: 112,
    sorter: (a, b) => compareText(a.category, b.category),
  },
  {
    title: "订单量",
    dataIndex: "orders",
    key: "orders",
    width: 88,
    sorter: numberSorter("orders"),
  },
  {
    title: "销量",
    dataIndex: "units",
    key: "units",
    width: 88,
    sorter: numberSorter("units"),
  },
  {
    title: "已收WFS费用",
    key: "chargedFee",
    width: 128,
    sorter: numberSorter("chargedFee"),
    render: moneyRender("chargedFee", currency),
  },
  {
    title: "应收WFS费用",
    key: "standardFee",
    width: 128,
    sorter: numberSorter("standardFee"),
    render: moneyRender("standardFee", currency),
  },
  {
    title: "多收金额",
    key: "overFee",
    width: 112,
    sorter: numberSorter("overFee"),
    render: (_, row) => <span className="wfs-fee-alert__danger-money">{formatWfsMoney(row.overFee, currency)}</span>,
  },
  {
    title: "单件多收",
    key: "unitOverFee",
    width: 112,
    sorter: numberSorter("unitOverFee"),
    render: (_, row) => <span className="wfs-fee-alert__danger-money">{formatWfsMoney(row.unitOverFee, currency)}</span>,
  },
  {
    title: "异常原因",
    dataIndex: "reason",
    key: "reason",
    width: 136,
    sorter: (a, b) => compareText(a.reason, b.reason),
  },
  {
    title: "优先级",
    key: "level",
    width: 96,
    render: (_, row) => <Tag color={priorityColor[row.level]}>{row.level}</Tag>,
  },
  {
    title: "Case状态",
    key: "status",
    width: 112,
    render: (_, row) => <StatusTagCell label={row.status} color={statusColor[row.status]} />,
  },
  {
    title: "Case编号",
    dataIndex: "caseNo",
    key: "caseNo",
    width: 136,
    render: (_, row) => row.caseNo || "-",
  },
  {
    title: "开Case时间",
    dataIndex: "caseOpenedAt",
    key: "caseOpenedAt",
    width: 112,
    render: (_, row) => row.caseOpenedAt || "-",
  },
  {
    title: "下次跟进",
    dataIndex: "nextFollowAt",
    key: "nextFollowAt",
    width: 112,
  },
  {
    title: "已追回金额",
    key: "recoveredAmount",
    width: 120,
    sorter: numberSorter("recoveredAmount"),
    render: moneyRender("recoveredAmount", currency),
  },
  {
    title: "最新跟进",
    key: "latestFollow",
    width: 220,
    ellipsis: true,
    render: (_, row) => <span title={row.latestFollow}>{row.latestFollow}</span>,
  },
  {
    title: "操作",
    key: "actions",
    width: 132,
    fixed: "right",
    render: (_, row) => (
      <Space size={4}>
        <Button type="link" onClick={() => onOpenFollow(row)}>编辑</Button>
        <Button type="link" onClick={() => onOpenDetail(row)}>详情</Button>
      </Space>
    ),
  },
];

const totalNumberKeys = new Set(["orders", "units"]);
const totalMoneyKeys = new Set(["chargedFee", "standardFee", "overFee", "recoveredAmount"]);

const sum = (rows: WfsFeeAlertRow[], key: keyof WfsFeeAlertRow) => rows
  .reduce((total, row) => total + Number(row[key]), 0);

function TotalCell({
  columnKey,
  currency,
  rows,
}: {
  columnKey: string;
  currency: WfsFeeAlertCurrency;
  rows: WfsFeeAlertRow[];
}) {
  if (columnKey === "image") return <span className="report-table-summary-label">总计</span>;
  if (columnKey === "sku") return <span>{rows.length.toLocaleString("zh-CN")} 个SKU</span>;
  if (totalNumberKeys.has(columnKey)) {
    return <span className="report-table-metric">{sum(rows, columnKey as keyof WfsFeeAlertRow).toLocaleString("zh-CN")}</span>;
  }
  if (totalMoneyKeys.has(columnKey)) {
    return <span>{formatWfsMoney(sum(rows, columnKey as keyof WfsFeeAlertRow), currency)}</span>;
  }
  if (columnKey === "unitOverFee") {
    const units = sum(rows, "units");
    const overFee = sum(rows, "overFee");
    return units ? <span>{formatWfsMoney(overFee / units, currency)}</span> : null;
  }
  return null;
}

function WfsFeeAlertTable({
  rows,
  currency,
  appliedColumnKeys,
  columnWidths,
  currentPage,
  pageSize,
  selectedRowKeys,
  onColumnWidthChange,
  onCurrentPageChange,
  onPageSizeChange,
  onSelectionChange,
  onBulkOpenCase,
  onBulkFollow,
  onCopy,
  onOpenDetail,
  onOpenFollow,
}: WfsFeeAlertTableProps) {
  const columnMap = new Map(createColumns(currency, onCopy, onOpenDetail, onOpenFollow).map((column) => [String(column.key), column]));
  const columns = appliedColumnKeys.flatMap((key) => {
    const column = columnMap.get(key);
    if (!column) return [];

    const title = wfsFeeAlertColumnFields.find((field) => field.key === key)?.title ?? key;
    const width = columnWidths[key] ?? (Number(column.width) || 96);
    const minWidth = Math.max(key === "image" ? 72 : key === "sku" ? 140 : 88, title.length * 14 + 28);

    return [{
      ...column,
      align: "left" as const,
      width,
      onHeaderCell: () => ({ className: "report-table-resizable-header-cell wfs-fee-alert__resizable-header-cell" }),
      title: (
        <ResizableColumnTitle
          label={title}
          minWidth={minWidth}
          width={width}
          onWidthChange={(nextWidth) => onColumnWidthChange(key, nextWidth)}
        />
      ),
    }];
  });

  return (
    <ReportTableShell className="wfs-fee-alert__table" label="WFS费用异常数据表">
      <ProTable<WfsFeeAlertRow>
        rowKey="id"
        columns={columns}
        dataSource={rows}
        rowSelection={{ fixed: true, selectedRowKeys, onChange: onSelectionChange }}
        search={false}
        options={false}
        toolBarRender={false}
        tableAlertRender={false}
        tableAlertOptionRender={false}
        bordered
        size="small"
        showSorterTooltip={{ target: "sorter-icon" }}
        scroll={{ x: "max-content", y: "100%" }}
        summary={() => (
          <Table.Summary fixed="bottom">
            <Table.Summary.Row className="wfs-fee-alert__total-row" data-testid="wfs-fee-alert-total-row">
              <Table.Summary.Cell index={0} />
              {columns.map((column, index) => {
                const key = String(column.key);
                return (
                  <Table.Summary.Cell
                    key={key}
                    index={index + 1}
                    align="left"
                    className={`wfs-fee-alert__total-cell wfs-fee-alert__total-cell--${key}`}
                  >
                    <TotalCell columnKey={key} currency={currency} rows={rows} />
                  </Table.Summary.Cell>
                );
              })}
            </Table.Summary.Row>
          </Table.Summary>
        )}
        footer={() => (
          <ReportTableSelectionBar
            selectedCount={selectedRowKeys.length}
            actions={[
              { key: "open-case", label: "批量开Case", onClick: onBulkOpenCase },
              { key: "follow", label: "批量跟进", onClick: onBulkFollow },
            ]}
          />
        )}
        pagination={{
          current: currentPage,
          pageSize,
          total: rows.length,
          showSizeChanger: true,
          showQuickJumper: true,
          pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS,
          showTotal: (total) => `共 ${total} 个异常SKU`,
          onChange: (nextPage, nextPageSize) => {
            if (nextPageSize !== pageSize) {
              onPageSizeChange(nextPageSize);
              return;
            }
            onCurrentPageChange(nextPage);
          },
        }}
        locale={{
          emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无WFS费用异常" />,
        }}
      />
    </ReportTableShell>
  );
}

export default WfsFeeAlertTable;
