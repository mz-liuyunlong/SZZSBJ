/** WFS fee alert No-API page: WFS overcharge, Case status and recovery tracking. */
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
import WfsFeeAlertDetailModal from "@/pages/warehouse/components/WfsFeeAlertDetailModal";
import WfsFeeAlertFollowModal from "@/pages/warehouse/components/WfsFeeAlertFollowModal";
import WfsFeeAlertSummaryCards from "@/pages/warehouse/components/WfsFeeAlertSummaryCards";
import WfsFeeAlertTable from "@/pages/warehouse/components/WfsFeeAlertTable";
import WfsFeeAlertToolbar from "@/pages/warehouse/components/WfsFeeAlertToolbar";
import {
  fetchWfsFeeAlerts,
  updateWfsFeeAlertCase,
} from "@/pages/warehouse/wfsFeeAlertApi";
import {
  createWfsFeeAlertInitialFilters,
  filterWfsFeeAlertRows,
  fixedWfsFeeAlertColumnKeys,
  wfsFeeAlertColumnFields,
  type WfsFeeAlertFilters,
  type WfsFeeAlertFollowFormValues,
  type WfsFeeAlertRow,
} from "@/pages/warehouse/wfsFeeAlertTypes";
import "@/pages/warehouse/WfsFeeAlertPage.css";

interface WfsFeeAlertPageProps {
  page: NavigationPage;
}

const EXPORT_PENDING = "WFS费用异常导出接口待接入";
const TEMPLATE_PENDING = "WFS费用异常列模板接口待接入";

const defaultColumnKeys = wfsFeeAlertColumnFields.map((field) => field.key);
const defaultColumnWidths: Record<string, number> = Object.fromEntries(wfsFeeAlertColumnFields.map((field) => [
  field.key,
  field.key === "image"
    ? 72
    : field.key === "sku"
      ? 154
      : field.key === "latestFollow"
        ? 220
        : field.key === "actions"
          ? 132
          : 112,
]));
const columnGroups = [{ title: "WFS费用异常字段", fields: wfsFeeAlertColumnFields }];
function WfsFeeAlertPage({ page }: WfsFeeAlertPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [filters, setFilters] = useState<WfsFeeAlertFilters>(createWfsFeeAlertInitialFilters);
  const [toolbarResetKey, setToolbarResetKey] = useState(0);
  const [statisticsVisible, setStatisticsVisible] = useState(true);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [appliedColumnKeys, setAppliedColumnKeys] = useState(defaultColumnKeys);
  const [columnWidths, setColumnWidths] = useState(defaultColumnWidths);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(REPORT_TABLE_DEFAULT_PAGE_SIZE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [detailRow, setDetailRow] = useState<WfsFeeAlertRow>();
  const [followRow, setFollowRow] = useState<WfsFeeAlertRow>();
  const [rows, setRows] = useState<WfsFeeAlertRow[]>([]);

  const reloadRows = async () => {
    try {
      const nextRows = await fetchWfsFeeAlerts(filters.dateRange[0], filters.dateRange[1]);
      setRows(nextRows);
    } catch {
      setRows([]);
      void messageApi.error("WFS费用异常数据加载失败");
    }
  };

  useEffect(() => {
    let cancelled = false;
    void fetchWfsFeeAlerts(filters.dateRange[0], filters.dateRange[1])
      .then((nextRows) => {
        if (!cancelled) setRows(nextRows);
      })
      .catch(() => {
        if (!cancelled) {
          setRows([]);
          void messageApi.error("WFS费用异常数据加载失败");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [filters.dateRange, messageApi]);

  const stores = useMemo(() => [...new Set(rows.map((row) => row.store))], [rows]);
  const owners = useMemo(() => [...new Set(rows.map((row) => row.owner))], [rows]);
  const reasons = useMemo(() => [...new Set(rows.map((row) => row.reason))], [rows]);
  const filteredRows = useMemo(() => filterWfsFeeAlertRows(rows, filters), [rows, filters]);

  const resetPageAndSelection = () => {
    setCurrentPage(1);
    setSelectedRowKeys([]);
  };

  const updateFilters = (nextFilters: WfsFeeAlertFilters) => {
    setFilters(nextFilters);
    resetPageAndSelection();
  };

  const resetFilters = () => {
    setFilters(createWfsFeeAlertInitialFilters());
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

  const handleBatchOpenCase = () => {
    if (!selectedRowKeys.length) {
      void messageApi.info("请先选择需要开Case的异常SKU");
      return;
    }
    const first = rows.find((row) => selectedRowKeys.includes(row.id));
    if (first) setFollowRow(first);
  };
  const handleBatchFollow = handleBatchOpenCase;

  const handleSaveFollow = async (values: WfsFeeAlertFollowFormValues) => {
    if (!followRow) return;
    try {
      await updateWfsFeeAlertCase(followRow.id, values, followRow.overFee);
      setFollowRow(undefined);
      await reloadRows();
      void messageApi.success("WFS异常跟进已保存");
    } catch {
      void messageApi.error("WFS异常跟进保存失败");
    }
  };

  const openFollowModal = (row: WfsFeeAlertRow) => {
    setDetailRow(undefined);
    setFollowRow(row);
  };

  const headerActions = (
    <>
    </>
  );

  const toolbarActions = (
    <Button
      icon={statisticsVisible ? <EyeInvisibleOutlined aria-hidden="true" /> : <EyeOutlined aria-hidden="true" />}
      onClick={() => setStatisticsVisible((visible) => !visible)}
    >
      {statisticsVisible ? "隐藏统计" : "显示统计"}
    </Button>
  );

  const toolbarIconActions = (
    <>
      <Tooltip title="列配置">
        <Button
          className="wfs-fee-alert__toolbar-icon-button"
          aria-label="列配置"
          icon={<SettingOutlined aria-hidden="true" />}
          onClick={() => setColumnConfigOpen(true)}
        />
      </Tooltip>
      <Tooltip title={EXPORT_PENDING}>
        <Button
          className="wfs-fee-alert__toolbar-icon-button"
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
      <div className="wfs-fee-alert">
        <section className="wfs-fee-alert__page-header" aria-label="WFS费用异常页面说明">
          <div>
            <Typography.Title level={3}>WFS费用异常总表</Typography.Title>
            <Typography.Paragraph type="secondary">
              按店铺/SKU统计WFS费用多收情况，快速查看多收金额、Case状态、追回金额和运营跟进信息。
            </Typography.Paragraph>
          </div>
        </section>

        <Card size="small" className="wfs-fee-alert__toolbar-card">
          <WfsFeeAlertToolbar
            key={toolbarResetKey}
            filters={filters}
            stores={stores}
            owners={owners}
            reasons={reasons}
            actions={toolbarActions}
            trailingActions={toolbarIconActions}
            onChange={updateFilters}
            onReset={resetFilters}
            onBatchOpenCase={handleBatchOpenCase}
            onBatchFollow={handleBatchFollow}
          />
        </Card>

        {statisticsVisible && <WfsFeeAlertSummaryCards rows={filteredRows} currency={filters.currency} />}

        <WfsFeeAlertTable
          rows={filteredRows}
          currency={filters.currency}
          appliedColumnKeys={appliedColumnKeys}
          columnWidths={columnWidths}
          currentPage={currentPage}
          pageSize={pageSize}
          selectedRowKeys={selectedRowKeys}
          onColumnWidthChange={(key, width) => setColumnWidths((current) => ({ ...current, [key]: width }))}
          onCurrentPageChange={setCurrentPage}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(normalizeReportTablePageSize(nextPageSize));
            resetPageAndSelection();
          }}
          onSelectionChange={setSelectedRowKeys}
          onBulkOpenCase={handleBatchOpenCase}
          onBulkFollow={handleBatchFollow}
          onCopy={(text) => void copyText(text)}
          onOpenDetail={setDetailRow}
          onOpenFollow={openFollowModal}
        />
      </div>

      <RuntimeColumnConfigDrawer
        open={columnConfigOpen}
        groups={columnGroups}
        fixedKeys={fixedWfsFeeAlertColumnKeys}
        defaultKeys={defaultColumnKeys}
        appliedKeys={appliedColumnKeys}
        onApply={setAppliedColumnKeys}
        onClose={() => setColumnConfigOpen(false)}
        onSaveTemplate={() => void messageApi.info(TEMPLATE_PENDING)}
      />
      <WfsFeeAlertDetailModal
        row={detailRow}
        currency={filters.currency}
        onClose={() => setDetailRow(undefined)}
        onOpenFollow={openFollowModal}
      />
      <WfsFeeAlertFollowModal
        row={followRow}
        currency={filters.currency}
        onClose={() => setFollowRow(undefined)}
        onSubmit={handleSaveFollow}
      />
    </PageShell>
  );
}

export default WfsFeeAlertPage;
