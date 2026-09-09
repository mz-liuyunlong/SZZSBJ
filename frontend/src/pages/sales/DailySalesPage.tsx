/** Daily-sales No-API shell composed from approved navigation metadata and local acceptance data. */
import {
  CloudDownloadOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  ReloadOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Button, Card, Tooltip, Typography, message } from "antd";
import { useMemo, useState, type Key } from "react";
import PageShell from "@/components/page/PageShell";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import type { NavigationPage } from "@/config/navigation";
import DailySalesCharts from "@/pages/sales/components/DailySalesCharts";
import DailySalesSummaryCards from "@/pages/sales/components/DailySalesSummaryCards";
import DailySalesTable from "@/pages/sales/components/DailySalesTable";
import DailySalesToolbar, {
  type DailySalesFilters,
} from "@/pages/sales/components/DailySalesToolbar";
import SalesDetailModal from "@/pages/sales/components/SalesDetailModal";
import { dailySalesMockData } from "@/pages/sales/dailySalesMockData";
import {
  dailySalesColumnFields,
  dateRangeForPreset,
  fixedDailySalesColumnKeys,
  type DailySalesRow,
} from "@/pages/sales/dailySalesTypes";
import "@/pages/sales/DailySalesPage.css";

const SYNC_PENDING = "同步接口待接入";
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
const owners = [...new Set(dailySalesMockData.map((row) => row.owner))];
const stores = [...new Set(dailySalesMockData.map((row) => row.store))];

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
  const [toolbarResetKey, setToolbarResetKey] = useState(0);
  const [statisticsVisible, setStatisticsVisible] = useState(true);
  const [chartsVisible, setChartsVisible] = useState(false);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState(defaultColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [detailRow, setDetailRow] = useState<DailySalesRow>();

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const filteredRows = useMemo(() => {
    const keyword = filters.keyword.trim().toLocaleLowerCase();
    return dailySalesMockData.filter((row) => {
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
      <Typography.Text className="daily-sales__sync-time" type="secondary">
        同步时间：待接入
      </Typography.Text>
      <Tooltip title={SYNC_PENDING}>
        <Button
          className="daily-sales__header-icon"
          type="text"
          shape="circle"
          aria-label="刷新每日销售"
          icon={<ReloadOutlined aria-hidden="true" />}
          onClick={() => void messageApi.info(SYNC_PENDING)}
        />
      </Tooltip>
    </>
  );

  const toolbarActions = (
    <>
      <Button
        icon={<CloudDownloadOutlined aria-hidden="true" />}
        onClick={() => void messageApi.info(EXPORT_PENDING)}
      >
        下载
      </Button>
      <Button
        icon={<SettingOutlined aria-hidden="true" />}
        onClick={() => setColumnConfigOpen(true)}
      >
        列配置
      </Button>
      <Button
        icon={statisticsVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
        onClick={() => setStatisticsVisible((visible) => !visible)}
      >
        {statisticsVisible ? "隐藏统计" : "显示统计"}
      </Button>
      <Button
        icon={chartsVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
        onClick={() => setChartsVisible((visible) => !visible)}
      >
        {chartsVisible ? "隐藏图表" : "显示图表"}
      </Button>
    </>
  );

  return (
    <PageShell page={page} headerActions={headerActions}>
      {messageContextHolder}
      <div className="daily-sales">
        <Card size="small" className="daily-sales__toolbar-card">
          <DailySalesToolbar
            key={toolbarResetKey}
            filters={filters}
            owners={owners}
            stores={stores}
            actions={toolbarActions}
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
            setPageSize(nextPageSize);
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
