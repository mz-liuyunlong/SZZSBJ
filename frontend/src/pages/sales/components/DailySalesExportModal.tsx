import { Button, Checkbox, DatePicker, Modal, Select, Space, Typography, message } from "antd";
import zhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/zh-cn";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  downloadDailySalesExportCsv,
  type DailySalesExportDimension,
  type DailySalesExportPeriod,
} from "@/pages/sales/dailySalesApi";

dayjs.locale("zh-cn");

interface DailySalesExportFilters {
  dateRange?: [string | null, string | null] | null;
  platforms: string[];
  owners: string[];
  stores: string[];
  searchField: string;
  keyword: string;
  batchValues?: string[];
}

interface DailySalesExportModalProps {
  open: boolean;
  filters: DailySalesExportFilters;
  onClose: () => void;
}

interface ExportColumnField {
  key: string;
  label: string;
}

interface ExportColumnGroup {
  title: string;
  fields: ExportColumnField[];
}

const exportColumnGroups: ExportColumnGroup[] = [
  {
    title: "基础信息",
    fields: [
      { key: "product_id", label: "商品ID" },
      { key: "product_name", label: "品名" },
      { key: "sku", label: "SKU" },
      { key: "msku", label: "MSKU" },
      { key: "store", label: "店铺" },
      { key: "owner", label: "负责人" },
      { key: "platform", label: "平台" },
    ],
  },
  {
    title: "销售信息",
    fields: [
      { key: "gross_sales_qty", label: "毛销量" },
      { key: "gross_order_count", label: "毛订单量" },
      { key: "gross_sales_amount", label: "毛销售额" },
      { key: "sales_qty", label: "销量" },
      { key: "order_count", label: "订单量" },
      { key: "sales_amount", label: "销售额" },
      { key: "avg_price", label: "平均售价" },
      { key: "sample_order_count", label: "送样单量" },
      { key: "sample_qty", label: "送样量" },
      { key: "sample_amount", label: "送样金额" },
    ],
  },
  {
    title: "退款信息",
    fields: [
      { key: "return_qty", label: "退款量" },
      { key: "refund_amount", label: "退款金额" },
      { key: "return_rate_30d", label: "退货率30天" },
    ],
  },
  {
    title: "广告信息",
    fields: [
      { key: "total_ad_spend", label: "总广告费" },
      { key: "ad_ratio", label: "广告占比" },
      { key: "ad_spend", label: "广告花费" },
      { key: "sem_ad_spend", label: "SEM广告费" },
    ],
  },
  {
    title: "成本信息",
    fields: [
      { key: "wfs_fee_total", label: "WFS总配送费" },
      { key: "wfs_low_price_surcharge", label: "低价配送附加费" },
      { key: "wfs_fee_unit", label: "WFS配送单价" },
      { key: "commission", label: "佣金" },
      { key: "purchase_cost_total", label: "采购总成本" },
      { key: "purchase_unit_cny", label: "采购单价" },
      { key: "first_leg_cost_total", label: "头程总成本" },
      { key: "first_leg_unit_cny", label: "头程单价" },
      { key: "storage_fee_total", label: "仓储费" },
      { key: "storage_unit", label: "仓储单价" },
      { key: "wfs_inventory", label: "WFS历史库存" },
      { key: "total_cost", label: "总成本" },
    ],
  },
  {
    title: "利润信息",
    fields: [
      { key: "order_profit", label: "订单利润" },
      { key: "avg_profit_per_order", label: "平均利润/单" },
      { key: "gross_margin", label: "利润率" },
      { key: "roi", label: "ROI" },
      { key: "cost_status", label: "成本状态" },
    ],
  },
];

const defaultExportColumns = exportColumnGroups.flatMap((group) =>
  group.fields.map((field) => field.key),
);

const dimensionOptions: Array<{ value: DailySalesExportDimension; label: string }> = [
  { value: "item_id", label: "商品ID" },
  { value: "msku", label: "MSKU" },
  { value: "sku", label: "SKU" },
];

const periodOptions: Array<{ value: DailySalesExportPeriod; label: string }> = [
  { value: "day", label: "按天" },
  { value: "month", label: "按月" },
];

const dimensionFieldKeyMap: Record<DailySalesExportDimension, string> = {
  item_id: "product_id",
  msku: "msku",
  sku: "sku",
};

const modalStyles: {
  panel: CSSProperties;
  fieldGrid: CSSProperties;
  headerActions: CSSProperties;
  headerActionButton: CSSProperties;
  clearActionButton: CSSProperties;
  headerActionDisabled: CSSProperties;
  selectedBadge: CSSProperties;
} = {
  panel: {
    border: "1px solid #e8edf5",
    borderRadius: 12,
    background: "#fbfcfe",
  },
  fieldGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  headerActions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  headerActionButton: {
    height: 30,
    padding: "0 12px",
    borderRadius: 8,
    border: "1px solid #d9e2f2",
    background: "#ffffff",
    color: "#4e5969",
    fontSize: 13,
    fontWeight: 500,
    boxShadow: "none",
  },
  clearActionButton: {
    border: "1px solid #b7d4ff",
    background: "#f7fbff",
    color: "#1677ff",
  },
  headerActionDisabled: {
    color: "#a8b1c2",
    background: "#f7f8fa",
    border: "1px solid #e5e6eb",
    opacity: 1,
    cursor: "not-allowed",
  },
  selectedBadge: {
    display: "inline-flex",
    alignItems: "center",
    height: 30,
    padding: "0 12px",
    borderRadius: 8,
    background: "#f0f7ff",
    border: "1px solid #b7d4ff",
    color: "#1677ff",
    fontSize: 13,
    fontWeight: 600,
  },
};

function normalizeRange(filters: DailySalesExportFilters): [Dayjs | null, Dayjs | null] {
  const start = filters.dateRange?.[0] ? dayjs(filters.dateRange[0]) : dayjs();
  const end = filters.dateRange?.[1] ? dayjs(filters.dateRange[1]) : start;
  return [start, end];
}

function DailySalesExportModal({ open, filters, onClose }: DailySalesExportModalProps) {
  const [messageApi, contextHolder] = message.useMessage();
  const [period, setPeriod] = useState<DailySalesExportPeriod>("day");
  const [dimension, setDimension] = useState<DailySalesExportDimension>("item_id");
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null]>(() =>
    normalizeRange(filters),
  );
  const [monthDate, setMonthDate] = useState<Dayjs | null>(() => normalizeRange(filters)[0]);
  const [selectedColumns, setSelectedColumns] = useState<string[]>(defaultExportColumns);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!open) return;

    const nextRange = normalizeRange(filters);
    queueMicrotask(() => {
      setPeriod("day");
      setDimension("item_id");
      setDateRange(nextRange);
      setMonthDate(nextRange[0]);
      setSelectedColumns(defaultExportColumns);
    });
  }, [filters, open]);

  const requiredDimensionColumn = dimensionFieldKeyMap[dimension];
  const effectiveSelectedColumns = useMemo(() => {
    const next = new Set(selectedColumns);
    next.add(requiredDimensionColumn);
    return defaultExportColumns.filter((key) => next.has(key));
  }, [requiredDimensionColumn, selectedColumns]);
  const selectedColumnSet = useMemo(
    () => new Set(effectiveSelectedColumns),
    [effectiveSelectedColumns],
  );
  const selectedCount = effectiveSelectedColumns.length;
  const dimensionLabel = dimensionOptions.find((option) => option.value === dimension)?.label ?? "商品ID";
  const periodLabel = periodOptions.find((option) => option.value === period)?.label ?? "按天";
  const exportDisabled = (
    period === "month"
      ? !monthDate || effectiveSelectedColumns.length === 0
      : !dateRange[0] || !dateRange[1] || effectiveSelectedColumns.length === 0
  );

  const toggleGroup = (group: ExportColumnGroup, checked: boolean) => {
    const groupKeys = group.fields.map((field) => field.key);
    setSelectedColumns((current) => {
      const next = new Set(current);

      for (const key of groupKeys) {
        if (checked) next.add(key);
        else next.delete(key);
      }

      next.add(requiredDimensionColumn);

      return defaultExportColumns.filter((key) => next.has(key));
    });
  };

  const toggleColumn = (key: string, checked: boolean) => {
    if (key === requiredDimensionColumn && !checked) return;

    setSelectedColumns((current) => {
      const next = new Set(current);

      if (checked) next.add(key);
      else next.delete(key);

      next.add(requiredDimensionColumn);

      return defaultExportColumns.filter((columnKey) => next.has(columnKey));
    });
  };

  const handleExport = async () => {
    if (exporting) return;

    if (period === "month" && !monthDate) {
      void messageApi.error("请选择月份");
      return;
    }

    if (period === "day" && (!dateRange[0] || !dateRange[1])) {
      void messageApi.error("请选择日期范围");
      return;
    }

    if (effectiveSelectedColumns.length === 0) {
      void messageApi.error("请至少选择一个表头");
      return;
    }

    const startDate = period === "month"
      ? monthDate!.startOf("month").format("YYYY-MM-DD")
      : dateRange[0]!.format("YYYY-MM-DD");
    const endDate = period === "month"
      ? monthDate!.endOf("month").format("YYYY-MM-DD")
      : dateRange[1]!.format("YYYY-MM-DD");

    setExporting(true);

    const exportRequest = downloadDailySalesExportCsv({
      startDate,
      endDate,
      period,
      dimension,
      columns: effectiveSelectedColumns,
      platforms: filters.platforms,
      owners: filters.owners,
      stores: filters.stores,
      searchField: filters.searchField,
      keyword: filters.keyword,
      batchValues: filters.batchValues,
    });

    onClose();

    try {
      await exportRequest;
      void messageApi.success("导出成功");
    } catch {
      void messageApi.error("导出失败，请稍后重试");
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      {contextHolder}

      <Modal
        title={(
          <Space size={12} align="baseline">
            <Typography.Text style={{ fontSize: 16, fontWeight: 700 }}>
              导出数据
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              配置导出范围与字段
            </Typography.Text>
          </Space>
        )}
        open={open}
        width={1060}
        footer={null}
        centered
        onCancel={onClose}
        styles={{
          body: {
            padding: 18,
            background: "#fff",
          },
        }}
      >
        <Space direction="vertical" size={18} style={{ width: "100%" }}>
          <div
            style={{
              ...modalStyles.panel,
              display: "grid",
              gridTemplateColumns: "176px 1fr 210px",
              gap: 12,
              padding: 14,
            }}
          >
            <div>
              <Typography.Text strong style={{ color: "#52627a" }}>
                日期粒度
              </Typography.Text>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  marginTop: 10,
                  padding: 2,
                  border: "1px solid #dbe3ef",
                  borderRadius: 8,
                  background: "#f4f6fa",
                }}
              >
                {periodOptions.map((option) => {
                  const active = period === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      disabled={exporting}
                      onClick={() => setPeriod(option.value)}
                      style={{
                        height: 40,
                        border: "none",
                        borderRadius: 7,
                        background: active ? "#fff" : "transparent",
                        color: active ? "#1677ff" : "#52627a",
                        fontSize: 14,
                        fontWeight: active ? 700 : 500,
                        boxShadow: active ? "0 2px 8px rgba(15, 35, 70, 0.08)" : "none",
                        cursor: exporting ? "not-allowed" : "pointer",
                      }}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <Typography.Text strong style={{ color: "#52627a" }}>
                日期范围
              </Typography.Text>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10 }}>
                {period === "month" ? (
                  <DatePicker
                    value={monthDate}
                    locale={zhCN}
                    picker="month"
                    format="YYYY年MM月"
                    placeholder="请选择月份"
                    disabled={exporting}
                    style={{ width: 220, height: 42 }}
                    onChange={(nextMonth) => setMonthDate(nextMonth)}
                  />
                ) : (
                  <>
                    <DatePicker
                      value={dateRange[0]}
                      locale={zhCN}
                      format="YYYY/MM/DD"
                      placeholder="开始日期"
                      disabled={exporting}
                      style={{ flex: 1, height: 42 }}
                      onChange={(nextDate) => setDateRange((current) => [nextDate, current[1]])}
                    />
                    <Typography.Text type="secondary">至</Typography.Text>
                    <DatePicker
                      value={dateRange[1]}
                      locale={zhCN}
                      format="YYYY/MM/DD"
                      placeholder="结束日期"
                      disabled={exporting}
                      style={{ flex: 1, height: 42 }}
                      onChange={(nextDate) => setDateRange((current) => [current[0], nextDate])}
                    />
                  </>
                )}
              </div>
            </div>

            <div>
              <Typography.Text strong style={{ color: "#52627a" }}>
                统计维度
              </Typography.Text>
              <Select
                value={dimension}
                options={dimensionOptions}
                disabled={exporting}
                style={{ width: "100%", height: 42, marginTop: 10 }}
                onChange={(nextDimension: DailySalesExportDimension) => {
                  setDimension(nextDimension);
                  const nextRequiredColumn = dimensionFieldKeyMap[nextDimension];
                  setSelectedColumns((current) => {
                    const next = new Set(current);
                    next.add(nextRequiredColumn);
                    return defaultExportColumns.filter((key) => next.has(key));
                  });
                }}
              />
            </div>
          </div>

          <div style={{ ...modalStyles.panel, overflow: "hidden" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "14px 16px",
                borderBottom: "1px solid #eef2f7",
              }}
            >
              <Space size={10} align="baseline">
                <Typography.Text style={{ fontSize: 16, fontWeight: 700 }}>
                  表头选择
                </Typography.Text>
</Space>

              <div style={modalStyles.headerActions}>
                <Button
                  type="default"
                  size="small"
                  disabled={exporting}
                  onClick={() => {
                    setSelectedColumns(
                      selectedCount === defaultExportColumns.length ? [requiredDimensionColumn] : defaultExportColumns,
                    );
                  }}
                  style={{
                    ...modalStyles.headerActionButton,
                    ...(selectedCount === defaultExportColumns.length
                      ? {}
                      : modalStyles.clearActionButton),
                  }}
                >
                  {selectedCount === defaultExportColumns.length ? "取消全选" : "全选所有"}
                </Button>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
              }}
            >
              {exportColumnGroups.map((group, index) => {
                const groupKeys = group.fields.map((field) => field.key);
                const checkedCount = groupKeys.filter((key) => selectedColumnSet.has(key)).length;
                const checked = checkedCount === groupKeys.length;
                const indeterminate = checkedCount > 0 && checkedCount < groupKeys.length;

                return (
                  <div
                    key={group.title}
                    style={{
                      minHeight: 126,
                      padding: "14px 16px",
                      borderRight: index % 2 === 0 ? "1px solid #f2f4f8" : "none",
                      borderBottom: index < exportColumnGroups.length - 2 ? "1px solid #f2f4f8" : "none",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "flex-start",
                        alignItems: "center",
                        marginBottom: 10,
                      }}
                    >
                      <Space size={8}>
                        <Checkbox
                          checked={checked}
                          indeterminate={indeterminate}
                          disabled={exporting}
                          onChange={(event) => toggleGroup(group, event.target.checked)}
                        />
                        <Typography.Text strong style={{ fontSize: 17 }}>
                          {group.title}
                        </Typography.Text>
                        <Typography.Text type="secondary">
                          {checkedCount}/{group.fields.length}
                        </Typography.Text>
                      </Space>

                      
                    </div>

                    <div style={modalStyles.fieldGrid}>
                      {group.fields.map((field) => {
                        const isDimension = requiredDimensionColumn === field.key;
                        const active = selectedColumnSet.has(field.key) || isDimension;

                        return (
                          <Checkbox
                            key={field.key}
                            checked={active}
                            disabled={exporting}
                            onChange={(event) => toggleColumn(field.key, event.target.checked)}
                            style={{
                              minHeight: 32,
                              width: "fit-content",
                              padding: "5px 9px",
                              border: "1px solid transparent",
                              borderRadius: 7,
                              background: active ? "#f9fbff" : "transparent",
                              color: active ? "#243044" : "#52627a",
                              fontWeight: 500,
                              display: "inline-flex",
                              alignItems: "center",
                              lineHeight: "20px",
                              whiteSpace: "nowrap",
                              boxShadow: "none",
                            }}
                          >
                            <Space size={5} align="center">
                              <span>{field.label}</span>
                              {isDimension && (
                                <Typography.Text style={{ color: "#6b86ad", fontSize: 12 }}>
                                  维度
                                </Typography.Text>
                              )}
                            </Space>
                          </Checkbox>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </Space>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            margin: "18px -18px -18px",
            padding: "12px 18px",
            borderTop: "1px solid #eef2f7",
            background: "#fff",
          }}
        >
          <Space size={6}>
            <Typography.Text type="secondary">已选</Typography.Text>
            <Typography.Text style={{ color: "#1677ff", fontSize: 16, fontWeight: 700 }}>
              {selectedCount}
            </Typography.Text>
            <Typography.Text type="secondary">项</Typography.Text>
            <Typography.Text type="secondary">·</Typography.Text>
            <Typography.Text type="secondary">{periodLabel}</Typography.Text>
            <Typography.Text type="secondary">·</Typography.Text>
            <Typography.Text type="secondary">{dimensionLabel}</Typography.Text>
          </Space>

          <Space size={12}>
            <Button disabled={exporting} onClick={onClose}>
              取消
            </Button>
            <Button
              type="primary"
              loading={exporting}
              disabled={exporting || exportDisabled}
              onClick={() => void handleExport()}
            >
              导出
            </Button>
          </Space>
        </div>
      </Modal>
    </>
  );
}

export default DailySalesExportModal;
