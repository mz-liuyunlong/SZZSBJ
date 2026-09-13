/** Order-profit No-API page: daily-sales layout, product-ID aggregation dimension. */
import {
  CloudDownloadOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Card, Tooltip, Typography, message } from "antd";
import { useMemo, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import OrderProfitCharts from "@/pages/sales/components/OrderProfitCharts";
import OrderProfitDetailModal from "@/pages/sales/components/OrderProfitDetailModal";
import OrderProfitSummaryCards from "@/pages/sales/components/OrderProfitSummaryCards";
import OrderProfitTable from "@/pages/sales/components/OrderProfitTable";
import OrderProfitToolbar, {
  type OrderProfitFilters,
} from "@/pages/sales/components/OrderProfitToolbar";
import { orderProfitSourceRecords } from "@/pages/sales/orderProfitMockData";
import {
  aggregateOrderProfitRows,
  dateRangeForPreset,
  fixedOrderProfitColumnKeys,
  orderProfitColumnFields,
  type OrderProfitRow,
  type OrderProfitSourceRecord,
} from "@/pages/sales/orderProfitTypes";
import "@/pages/sales/OrderProfitPage.css";

const EXPORT_PENDING = "导出接口待接入";
const TEMPLATE_PENDING = "列模板接口待接入";

const createInitialFilters = (): OrderProfitFilters => ({
  platforms: [],
  owners: [],
  stores: [],
  currency: "USD",
  datePreset: "today",
  dateRange: dateRangeForPreset("today"),
  searchField: "productId",
  keyword: "",
});

const defaultColumnKeys = orderProfitColumnFields.map((field) => field.key);
const defaultColumnWidths: Record<string, number> = Object.fromEntries(orderProfitColumnFields.map((field) => [
  field.key,
  field.key === "image" || field.key === "analysis"
    ? 72
    : field.key === "productIdName"
      ? 240
      : field.key === "skuMsku"
        ? 190
        : field.key === "actions"
          ? 96
          : 112,
]));
const columnGroups = [{ title: "订单利润字段", fields: orderProfitColumnFields }];
const owners = [...new Set(orderProfitSourceRecords.map((row) => row.owner))];
const stores = [...new Set(orderProfitSourceRecords.map((row) => row.store))];

const matchesDate = (row: OrderProfitSourceRecord, filters: OrderProfitFilters) => {
  if (filters.dateRange) {
    return row.date >= filters.dateRange[0] && row.date <= filters.dateRange[1];
  }
  return true;
};

interface OrderProfitPageProps {
  page: NavigationPage;
}

function OrderProfitPage({ page }: OrderProfitPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [filters, setFilters] = useState(createInitialFilters);
  const [toolbarResetKey, setToolbarResetKey] = useState(0);
  const [statisticsVisible, setStatisticsVisible] = useState(true);
  const [chartsVisible, setChartsVisible] = useState(false);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState(defaultColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [detailRow, setDetailRow] = useState<OrderProfitRow>();

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const filteredSourceRecords = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    return orderProfitSourceRecords.filter((row) => {
      const target = String(row[filters.searchField]).toLocaleLowerCase();
      const exactTarget = String(row[filters.searchField]);
      return (filters.platforms.length === 0 || filters.platforms.includes(row.platform))
        && (filters.owners.length === 0 || filters.owners.includes(row.owner))
        && (filters.stores.length === 0 || filters.stores.includes(row.store))
        && matchesDate(row, filters)
        && (!keyword || target.includes(keyword))
        && (!filters.batchValues?.length || filters.batchValues.includes(exactTarget));
    });
  }, [filters]);

  const filteredRows = useMemo(() => aggregateOrderProfitRows(filteredSourceRecords), [filteredSourceRecords]);

  const updateFilters = (nextFilters: OrderProfitFilters) => {
    setFilters(nextFilters);
    resetPageAndSelection();
  };

  const resetFilters = () => {
    setFilters(createInitialFilters());
    setToolbarResetKey((current) => current + 1);
    resetPageAndSelection();
  };

  const copyText = async (text: string) => {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(text);
      void messageApi.success("已复制");
    } catch {
      void messageApi.error("复制失败，请手动复制");
    }
  };

  const headerActions = (
    <>
    </>
  );

  const toolbarActions = (
    <>
      <Button
        icon={statisticsVisible ? <EyeInvisibleOutlined aria-hidden="true" /> : <EyeOutlined aria-hidden="true" />}
        onClick={() => setStatisticsVisible((visible) => !visible)}
      >
        {statisticsVisible ? "隐藏统计" : "显示统计"}
      </Button>
      <Button
        icon={chartsVisible ? <EyeInvisibleOutlined aria-hidden="true" /> : <EyeOutlined aria-hidden="true" />}
        onClick={() => setChartsVisible((visible) => !visible)}
      >
        {chartsVisible ? "隐藏图表" : "显示图表"}
      </Button>
    </>
  );

  const toolbarIconActions = (
    <>
      <Tooltip title="列配置">
        <Button
          className="order-profit__toolbar-icon-button"
          aria-label="列配置"
          icon={<SettingOutlined aria-hidden="true" />}
          onClick={() => setColumnConfigOpen(true)}
        />
      </Tooltip>
      <Tooltip title={EXPORT_PENDING}>
        <Button
          className="order-profit__toolbar-icon-button"
          aria-label="下载"
          icon={<CloudDownloadOutlined aria-hidden="true" />}
          onClick={() => void messageApi.info(EXPORT_PENDING)}
        />
      </Tooltip>
    </>
  );

  return (
    <PageShell page={page} headerActions={headerActions}>
      {messageContextHolder}
      <div className="order-profit">
        <section className="order-profit__page-header" aria-label="订单利润页面说明">
          <div>
            <Typography.Title level={3}>订单利润</Typography.Title>
            <Typography.Paragraph type="secondary">
              按商品ID汇总订单量、销售额、成本费用、广告花费与订单利润，口径与每日销售保持一致。
            </Typography.Paragraph>
          </div>
        </section>

        <Card size="small" className="order-profit__toolbar-card">
          <OrderProfitToolbar
            key={toolbarResetKey}
            filters={filters}
            owners={owners}
            stores={stores}
            actions={toolbarActions}
            trailingActions={toolbarIconActions}
            onChange={updateFilters}
            onReset={resetFilters}
            onMessage={(content) => void messageApi.info(content)}
          />
        </Card>

        {statisticsVisible && <OrderProfitSummaryCards rows={filteredRows} currency={filters.currency} />}
        {chartsVisible && <OrderProfitCharts records={filteredSourceRecords} currency={filters.currency} />}

        <OrderProfitTable
          rows={filteredRows}
          currency={filters.currency}
          appliedColumnKeys={appliedColumnKeys}
          columnWidths={columnWidths}
          currentPage={currentPage}
          pageSize={pageSize}
          selectedRowKeys={selectedRowKeys}
          onColumnWidthChange={(key, width) => setColumnWidths((current) => ({
            ...current,
            [key]: width,
          }))}
          onCurrentPageChange={setCurrentPage}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(normalizeReportTablePageSize(nextPageSize));
            resetPageAndSelection();
          }}
          onSelectionChange={setSelectedRowKeys}
          onBulkExport={() => void messageApi.info(EXPORT_PENDING)}
          onCopy={(text) => void copyText(text)}
          onOpenDetail={setDetailRow}
        />
      </div>

      <RuntimeColumnConfigDrawer
        open={columnConfigOpen}
        groups={columnGroups}
        fixedKeys={fixedOrderProfitColumnKeys}
        defaultKeys={defaultColumnKeys}
        appliedKeys={appliedColumnKeys}
        onApply={setAppliedColumnKeys}
        onClose={() => setColumnConfigOpen(false)}
        onSaveTemplate={() => void messageApi.info(TEMPLATE_PENDING)}
      />
      <OrderProfitDetailModal row={detailRow} onClose={() => setDetailRow(undefined)} />
    </PageShell>
  );
}

export default OrderProfitPage;
