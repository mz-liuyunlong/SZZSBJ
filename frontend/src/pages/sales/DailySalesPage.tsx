/** Daily-sales page backed by DATA-PAGES MART API with temporary local fallback. */
import {
  CloudDownloadOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Card, Tooltip, Typography, message } from "antd";
import { useEffect, useMemo, useState, type Key } from "react";
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
import { fetchDailySalesRows } from "@/pages/sales/dailySalesApi";
import { dailySalesMockData } from "@/pages/sales/dailySalesMockData";
import {
  dailySalesColumnFields,
  dateRangeForPreset,
  fixedDailySalesColumnKeys,
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
  datePreset: "today",
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

const matchesDate = (row: DailySalesRow, filters: DailySalesFilters) => {
  if (filters.dateRange) {
    return row.date >= filters.dateRange[0] && row.date <= filters.dateRange[1];
  }
  return true;
};

interface DailySalesPageProps {
  page: NavigationPage;
}

function DailySalesPage({ page }: DailySalesPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [filters, setFilters] = useState(createInitialFilters);
  const [sourceRows, setSourceRows] = useState<DailySalesRow[]>(dailySalesMockData);
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

  const dateRangeStart = filters.dateRange?.[0];
  const dateRangeEnd = filters.dateRange?.[1];

  useEffect(() => {
    let active = true;
    void fetchDailySalesRows({
      startDate: dateRangeStart,
      endDate: dateRangeEnd,
      pageSize: 500,
    })
      .then(({ rows }) => {
        if (active) setSourceRows(rows);
      })
      .catch(() => {
        // Keep the local fallback visible until the backend has synced MART data.
      });
    return () => {
      active = false;
    };
  }, [dateRangeStart, dateRangeEnd]);

  const owners = useMemo(() => [...new Set(sourceRows.map((row) => row.owner))], [sourceRows]);
  const stores = useMemo(() => [...new Set(sourceRows.map((row) => row.store))], [sourceRows]);

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const filteredRows = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    return sourceRows.filter((row) => {
      const target = String(row[filters.searchField]).toLocaleLowerCase();
      const exactTarget = String(row[filters.searchField]);
      return (filters.platforms.length === 0 || filters.platforms.includes(row.platform))
        && (filters.owners.length === 0 || filters.owners.includes(row.owner))
        && (filters.stores.length === 0 || filters.stores.includes(row.store))
        && matchesDate(row, filters)
        && (!keyword || target.includes(keyword))
        && (!filters.batchValues?.length || filters.batchValues.includes(exactTarget));
    });
  }, [filters, sourceRows]);

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
      <div className="daily-sales">
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

        {statisticsVisible && <DailySalesSummaryCards rows={filteredRows} currency={filters.currency} />}
        {chartsVisible && <DailySalesCharts rows={filteredRows} currency={filters.currency} />}

        <DailySalesTable
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
