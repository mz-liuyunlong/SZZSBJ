/** API-connected WFS fee evidence, case status and recovery tracking. */
import {
  CloudDownloadOutlined,
  ExperimentOutlined,
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
import { hasPermission } from "@/shared/permissions/mockAccess";
import WfsFeeAlertDetailModal from "@/pages/warehouse/components/WfsFeeAlertDetailModal";
import WfsAbandonRequestModal from "@/pages/warehouse/components/WfsAbandonRequestModal";
import WfsFeeAlertSummaryCards from "@/pages/warehouse/components/WfsFeeAlertSummaryCards";
import WfsFeeAlertTable from "@/pages/warehouse/components/WfsFeeAlertTable";
import WfsFeeAlertToolbar from "@/pages/warehouse/components/WfsFeeAlertToolbar";
import {
  fetchWfsFeeAlerts,
  markWfsFeeCaseRecovered,
  previewWfsFeeDetection,
  updateWfsFeeAlertCase,
} from "@/pages/warehouse/wfsFeeAlertApi";
import {
  createWfsFeeAlertInitialFilters,
  defaultWfsDetectionWindow,
  filterWfsFeeAlertRows,
  fixedWfsFeeAlertColumnKeys,
  wfsFeeAlertColumnFields,
  type WfsFeeAlertFilters,
  type WfsFeeAlertFollowFormValues,
  type WfsFeeRecoveredFormValues,
  type WfsFeeAlertRow,
} from "@/pages/warehouse/wfsFeeAlertTypes";
import "@/pages/warehouse/WfsFeeAlertPage.css";

interface WfsFeeAlertPageProps {
  page: NavigationPage;
  permissions: readonly string[];
}

const EXPORT_PENDING = "WFS费用异常导出接口待接入";
const TEMPLATE_PENDING = "WFS费用异常列模板接口待接入";

const defaultColumnKeys = wfsFeeAlertColumnFields.map((field) => field.key);
const defaultColumnWidths: Record<string, number> = Object.fromEntries(wfsFeeAlertColumnFields.map((field) => [
  field.key,
  field.key === "image"
    ? 72
    : field.key === "productIdName"
      ? 240
      : field.key === "skuMsku"
      ? 190
      : field.key === "store"
        ? 148
        : field.key === "latestFollow"
          ? 220
          : field.key === "actions"
            ? 132
            : 112,
]));
const columnGroups = [{ title: "WFS费用异常字段", fields: wfsFeeAlertColumnFields }];
function WfsFeeAlertPage({ page, permissions }: WfsFeeAlertPageProps) {
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
  const [abandonRow, setAbandonRow] = useState<WfsFeeAlertRow>();
  const [rows, setRows] = useState<WfsFeeAlertRow[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [settledRangeKey, setSettledRangeKey] = useState<string | null>(null);
  const [rangeStart, rangeEnd] = filters.dateRange;
  const requestedRangeKey = JSON.stringify([rangeStart, rangeEnd]);
  const loading = settledRangeKey !== requestedRangeKey;
  const canFollow = hasPermission(permissions, "action:warehouse:wfs-fee-alert:follow");
  const canMarkRecovered = hasPermission(permissions, "action:warehouse:wfs-fee-alert:mark-recovered");
  const canArchiveRequest = hasPermission(
    permissions,
    "action:warehouse:wfs-fee-alert:archive-request",
  );
  const canPreviewDetection = hasPermission(permissions, "action:warehouse:wfs-fee-alert:sync-legacy");

  const handleDetectionPreview = async () => {
    if (!canPreviewDetection || previewLoading) return;
    const [fallbackStart, fallbackEnd] = defaultWfsDetectionWindow();
    setPreviewLoading(true);
    try {
      const result = await previewWfsFeeDetection(
        filters.dateRange[0] || fallbackStart,
        filters.dateRange[1] || fallbackEnd,
      );
      void messageApi.info(
        `预览完成：${result.scanned_stores} 个店铺、${result.scanned_skus} 个 SKU，` +
        `${result.would_create} 个拟新增、${result.already_exists} 个已有、` +
        `${result.review_required} 个待复核、${result.failed} 个失败。未写入案件。`,
        8,
      );
    } catch {
      void messageApi.error("WFS 检测预览失败，未执行任何写入");
    } finally {
      setPreviewLoading(false);
    }
  };

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

    void fetchWfsFeeAlerts(rangeStart, rangeEnd)
      .then((nextRows) => {
        if (!cancelled) {
          setRows(nextRows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRows([]);
          void messageApi.error("WFS费用异常数据加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSettledRangeKey(requestedRangeKey);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [rangeStart, rangeEnd, requestedRangeKey, messageApi]);

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

  const handleBatchOpenCase = () => { void messageApi.info("批量开Case暂未接入，请单条编辑"); };

  const handleSaveFollow = async (
    values: WfsFeeAlertFollowFormValues,
  ): Promise<void> => {
    if (!detailRow || !canFollow) {
      throw new Error("当前无跟进权限或未选择记录");
    }

    const caseId = detailRow.id;
    try {
      await updateWfsFeeAlertCase(caseId, values);
    } catch {
      void messageApi.error("WFS跟进保存失败");
      throw new Error("WFS跟进保存失败");
    }

    void messageApi.success("跟进已保存，历史记录不可删除");
    try {
      const nextRows = await fetchWfsFeeAlerts(
        filters.dateRange[0],
        filters.dateRange[1],
      );
      setRows(nextRows);
      setDetailRow(nextRows.find((row) => row.id === caseId));
    } catch {
      void messageApi.warning("保存成功，但刷新失败，请重新打开详情");
    }
  };


  const handleMarkRecovered = async (values: WfsFeeRecoveredFormValues): Promise<void> => {
    if (!detailRow || !canMarkRecovered) {
      throw new Error("当前无追回确认权限或未选择记录");
    }
    try {
      await markWfsFeeCaseRecovered(detailRow.id, values);
    } catch {
      void messageApi.error("标记已追回失败，请核对案件状态和追回金额");
      throw new Error("标记已追回失败");
    }
    void messageApi.success("已登记追回金额，案件状态已更新为已追回");
    setDetailRow(undefined);
    await reloadRows();
  };

  const headerActions = (
    <>
      {canPreviewDetection && (
        <Button
          icon={<ExperimentOutlined aria-hidden="true" />}
          loading={previewLoading}
          onClick={() => void handleDetectionPreview()}
        >
          检测预览
        </Button>
      )}
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
          />
        </Card>

        {statisticsVisible && <WfsFeeAlertSummaryCards rows={filteredRows} currency={filters.currency} />}

        <WfsFeeAlertTable
          loading={loading}
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
          onCopy={(text) => void copyText(text)}
          onOpenDetail={setDetailRow}
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
        onSubmit={handleSaveFollow}
        onMarkRecovered={handleMarkRecovered}
        canFollow={canFollow}
        canMarkRecovered={canMarkRecovered}
        canArchiveRequest={canArchiveRequest}
        onOpenAbandon={(row) => { setDetailRow(undefined); setAbandonRow(row); }}
      />
      <WfsAbandonRequestModal
        row={canArchiveRequest ? abandonRow : undefined}
        onClose={() => setAbandonRow(undefined)}
        onSuccess={() => void reloadRows()}
      />
    </PageShell>
  );
}

export default WfsFeeAlertPage;
