/** Daily-sales page backed by DATA-PAGES MART API. */
import {
  CloudDownloadOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Card, Tooltip, Typography, message } from "antd";
import { useEffect, useMemo, useRef, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import {
  REPORT_TABLE_DEFAULT_PAGE_SIZE,
  normalizeReportTablePageSize,
} from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import DailySalesCharts from "@/pages/sales/components/DailySalesCharts";
import DailySalesSummaryCards from "@/pages/sales/components/DailySalesSummaryCards";
import DailySalesTable from "@/pages/sales/components/DailySalesTable";
import DailySalesToolbar, {
  type DailySalesFilters,
} from "@/pages/sales/components/DailySalesToolbar";
import SalesDetailModal from "@/pages/sales/components/SalesDetailModal";
import { fetchDailySalesRows, type DailySalesServerSummary } from "@/pages/sales/dailySalesApi";
import {
  dailySalesColumnFields,
  dateRangeForPreset,
  fixedDailySalesColumnKeys,
  type DailySalesRefundSummary,
  type DailySalesRow,
} from "@/pages/sales/dailySalesTypes";
import "@/pages/sales/DailySalesPage.css";

const EXPORT_PENDING = "导出接口待接入";

const TEMPLATE_PENDING = "列模板接口待接入";

const createInitialFilters = (): DailySalesFilters => ({
  platforms: [],
  owners: [],
  stores: [],
  currency: "USD",
  datePreset: "custom",
  dateRange: dateRangeForPreset("today"),
  searchField: "sku",
  keyword: "",
});

const defaultColumnKeys = dailySalesColumnFields.map((field) => field.key);
const defaultColumnWidths = Object.fromEntries(dailySalesColumnFields.map((field) => [
  field.key,
  field.key === "image" || field.key === "analysis"
    ? 72
    : field.key === "mskuProductId" || field.key === "skuProductName"
      ? 210
      : field.key.includes("Log")
        ? 180
        : 112,
]));
const columnGroups = [{ title: "每日销售字段", fields: dailySalesColumnFields }];


interface DailySalesPageProps {
  page: NavigationPage;
}

function DailySalesPage({ page }: DailySalesPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const dailySalesPageRootRef = useRef<HTMLDivElement | null>(null);
  const [filters, setFilters] = useState(createInitialFilters);
  const [serverTotal, setServerTotal] = useState(0);
  const [sourceRows, setSourceRows] = useState<DailySalesRow[]>([]);
  const [refundSummary, setRefundSummary] = useState<DailySalesRefundSummary | null>(null);
  const [salesSummary, setSalesSummary] = useState<DailySalesServerSummary | null>(null);
  const [toolbarResetKey, setToolbarResetKey] = useState(0);
  const [statisticsVisible, setStatisticsVisible] = useState(true);
  const [chartsVisible, setChartsVisible] = useState(false);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState(defaultColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [detailRow, setDetailRow] = useState<DailySalesRow>();
  const [isTableRequesting, setIsTableRequesting] = useState(false);
  const dateRangeStart = filters.dateRange?.[0];
  const dateRangeEnd = filters.dateRange?.[1];


  // DAILY_SALES_RESET_FILTERS_ON_MOUNT
  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    queueMicrotask(() => {
      if (active) setIsTableRequesting(true);
    });
    void fetchDailySalesRows({
      startDate: dateRangeStart,
      endDate: dateRangeEnd,
      page: currentPage,
      pageSize,
      signal: controller.signal,
    })
      .then(({ rows, summary: nextSalesSummary, refundSummary: nextRefundSummary, meta }) => {
        if (!active) return;
        setSourceRows(Array.isArray(rows) ? rows : []);
        setServerTotal(meta.total);
        setSalesSummary(nextSalesSummary);
        setRefundSummary(nextRefundSummary);
      })
      .catch((reason: unknown) => {
        if (!active || (reason instanceof Error && reason.name === "AbortError")) return;
        setSourceRows([]);
        setServerTotal(0);
        setSalesSummary(null);
        setRefundSummary(null);
      })
      .finally(() => {
        if (active) setIsTableRequesting(false);
      });

    return () => {
      active = false;
      controller.abort();
      setIsTableRequesting(false);
    };
  }, [currentPage, dateRangeStart, dateRangeEnd, pageSize]);

  const safeSourceRows = Array.isArray(sourceRows) ? sourceRows : [];

  const owners = useMemo(() => [...new Set(safeSourceRows.map((row) => row.owner))], [safeSourceRows]);
  const stores = useMemo(() => [...new Set(safeSourceRows.map((row) => row.store))], [safeSourceRows]);

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const filteredRows = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    return safeSourceRows.filter((row) => {
      const target = String(row[filters.searchField]).toLocaleLowerCase();
      const exactTarget = String(row[filters.searchField]);
      return (filters.platforms.length === 0 || filters.platforms.includes(row.platform))
        && (filters.owners.length === 0 || filters.owners.includes(row.owner))
        && (filters.stores.length === 0 || filters.stores.includes(row.store))
        && (!keyword || target.includes(keyword))
        && (!filters.batchValues?.length || filters.batchValues.includes(exactTarget));
    });
  }, [filters, safeSourceRows]);

  const updateFilters = (nextFilters: DailySalesFilters) => {
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
          className="daily-sales__toolbar-icon-button"
          aria-label="列配置"
          icon={<SettingOutlined aria-hidden="true" />}
          onClick={() => setColumnConfigOpen(true)}
        />
      </Tooltip>
      <Tooltip title={EXPORT_PENDING}>
        <Button
          className="daily-sales__toolbar-icon-button"
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
      <div ref={dailySalesPageRootRef} className="daily-sales">
        <section className="daily-sales__page-header" aria-label="每日销售页面说明">
          <div>
            <Typography.Title level={3}>每日销售</Typography.Title>
            <Typography.Paragraph type="secondary">
              按日期查看 SKU / MSKU 销售、成本、利润、广告费、库存与运营日志数据。
            </Typography.Paragraph>
          </div>
        </section>
          <Card size="small" className="daily-sales__toolbar-card">
          <DailySalesToolbar
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

        {statisticsVisible && (
          <DailySalesSummaryCards
            rows={filteredRows}
            currency={filters.currency}
            refundSummary={refundSummary}
          serverSummary={salesSummary}
          />
        )}
        {chartsVisible && <DailySalesCharts rows={filteredRows} currency={filters.currency} />}


            <DailySalesTable
          rows={filteredRows}
          total={serverTotal || filteredRows.length}
          loading={isTableRequesting}
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
        fixedKeys={fixedDailySalesColumnKeys}
        defaultKeys={defaultColumnKeys}
        appliedKeys={appliedColumnKeys}
        onApply={setAppliedColumnKeys}
        onClose={() => setColumnConfigOpen(false)}
        onSaveTemplate={() => void messageApi.info(TEMPLATE_PENDING)}
      />
      <SalesDetailModal row={detailRow} onClose={() => setDetailRow(undefined)} />
    </PageShell>
  );
}

export default DailySalesPage;
