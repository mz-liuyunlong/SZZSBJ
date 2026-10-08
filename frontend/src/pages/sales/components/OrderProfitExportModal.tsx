import { Button, Checkbox, DatePicker, Modal, Select, Space, Typography, message } from "antd";
import zhCN from "antd/es/date-picker/locale/zh_CN";
import dayjs, { type Dayjs } from "dayjs";
import "dayjs/locale/zh-cn";
import { useEffect, useMemo, useState } from "react";
import {
  downloadOrderProfitExportCsv,
  type OrderProfitExportDimension,
  type OrderProfitExportPeriod,
} from "@/pages/sales/orderProfitApi";

dayjs.locale("zh-cn");

const { RangePicker } = DatePicker;

interface OrderProfitExportFilters {
  dateRange?: [string | null, string | null] | null;
  platforms: string[];
  owners: string[];
  stores: string[];
  searchField: string;
  keyword: string;
}

interface OrderProfitExportModalProps {
  open: boolean;
  filters: OrderProfitExportFilters;
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
    title: "基础字段",
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
    title: "销售字段",
    fields: [
      { key: "sales_qty", label: "销量" },
      { key: "order_count", label: "订单量" },
      { key: "sales_amount", label: "销售额" },
      { key: "avg_price", label: "平均售价" },
      { key: "sample_qty", label: "送样量" },
      { key: "sample_amount", label: "送样金额" },
    ],
  },
  {
    title: "退款字段",
    fields: [
      { key: "return_qty", label: "退款量" },
      { key: "refund_amount", label: "退款金额" },
      { key: "return_rate_30d", label: "退货率30天" },
    ],
  },
  {
    title: "广告字段",
    fields: [
      { key: "total_ad_spend", label: "总广告费" },
      { key: "ad_ratio", label: "广告占比" },
      { key: "ad_spend", label: "广告花费" },
      { key: "sem_ad_spend", label: "SEM广告费" },
    ],
  },
  {
    title: "成本字段",
    fields: [
      { key: "wfs_fee_total", label: "WFS总配送费" },
      { key: "wfs_fee_unit", label: "WFS配送单价" },
      { key: "commission", label: "佣金" },
      { key: "purchase_cost_total", label: "采购总成本" },
      { key: "purchase_unit_cny", label: "采购单价" },
      { key: "first_leg_cost_total", label: "头程总成本" },
      { key: "first_leg_unit_cny", label: "头程单价" },
      { key: "storage_fee_total", label: "仓储费" },
      { key: "storage_unit", label: "仓储单价" },
      { key: "wfs_inventory", label: "WFS实时库存" },
      { key: "total_cost", label: "总成本" },
    ],
  },
  {
    title: "利润字段",
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

const dimensionOptions: Array<{ value: OrderProfitExportDimension; label: string }> = [
  { value: "msku", label: "按MSKU" },
  { value: "item_id", label: "按商品ID" },
  { value: "sku", label: "按SKU" },
];

const periodOptions: Array<{ value: OrderProfitExportPeriod; label: string }> = [
  { value: "day", label: "按天" },
  { value: "month", label: "按月" },
];

function normalizeRange(filters: OrderProfitExportFilters): [Dayjs | null, Dayjs | null] {
  const start = filters.dateRange?.[0] ? dayjs(filters.dateRange[0]) : dayjs();
  const end = filters.dateRange?.[1] ? dayjs(filters.dateRange[1]) : start;
  return [start, end];
}

function OrderProfitExportModal({ open, filters, onClose }: OrderProfitExportModalProps) {
  const [messageApi, contextHolder] = message.useMessage();
  const [period, setPeriod] = useState<OrderProfitExportPeriod>("day");
  const [dimension, setDimension] = useState<OrderProfitExportDimension>("msku");
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null]>(() =>
    normalizeRange(filters),
  );
  const [monthDate, setMonthDate] = useState<Dayjs | null>(() => normalizeRange(filters)[0]);
  const [selectedColumns, setSelectedColumns] = useState<string[]>(defaultExportColumns);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let active = true;

    if (open) {
      const nextRange = normalizeRange(filters);

      queueMicrotask(() => {
        if (!active) return;

        setPeriod("day");
        setDimension("msku");
        setDateRange(nextRange);
        setMonthDate(nextRange[0]);
        setSelectedColumns(defaultExportColumns);
      });
    }

    return () => {
      active = false;
    };
  }, [filters, open]);

  const selectedColumnSet = useMemo(() => new Set(selectedColumns), [selectedColumns]);
  const exportDisabled = (
    period === "month"
      ? !monthDate || selectedColumns.length === 0
      : !dateRange[0] || !dateRange[1] || selectedColumns.length === 0
  );

  const toggleGroup = (group: ExportColumnGroup, checked: boolean) => {
    const groupKeys = group.fields.map((field) => field.key);
    setSelectedColumns((current) => {
      const next = new Set(current);

      for (const key of groupKeys) {
        if (checked) next.add(key);
        else next.delete(key);
      }

      return defaultExportColumns.filter((key) => next.has(key));
    });
  };

  const toggleColumn = (key: string, checked: boolean) => {
    setSelectedColumns((current) => {
      const next = new Set(current);

      if (checked) next.add(key);
      else next.delete(key);

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

    if (selectedColumns.length === 0) {
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

    const exportRequest = downloadOrderProfitExportCsv({
      startDate,
      endDate,
      period,
      dimension,
      columns: selectedColumns,
      platforms: filters.platforms,
      owners: filters.owners,
      stores: filters.stores,
      searchField: filters.searchField,
      keyword: filters.keyword,
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
        title="导出"
        open={open}
        width={1040}
        onCancel={onClose}
        footer={[
          <Button key="cancel" disabled={exporting} onClick={onClose}>
            取消
          </Button>,
          <Button
            key="export"
            type="primary"
            loading={exporting}
            disabled={exporting || exportDisabled}
            onClick={() => void handleExport()}
          >
            导出
          </Button>,
        ]}
      >
        <Space direction="vertical" size={22} style={{ width: "100%" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 28,
            }}
          >
            <div>
              <Typography.Text>日期范围：</Typography.Text>
              <Space.Compact style={{ width: "100%", marginTop: 8 }}>
                <Select
                  value={period}
                  options={periodOptions}
                  style={{ width: 110 }}
                  disabled={exporting}
                  onChange={setPeriod}
                />
                {period === "month" ? (
                  <DatePicker
                    value={monthDate}
                    locale={zhCN}
                    picker="month"
                    format="YYYY年MM月"
                    placeholder="请选择月份"
                    disabled={exporting}
                    style={{ width: "100%" }}
                    onChange={(nextMonth) => setMonthDate(nextMonth)}
                  />
                ) : (
                  <RangePicker
                    value={dateRange}
                    locale={zhCN}
                    format="YYYY年MM月DD日"
                    disabled={exporting}
                    style={{ width: "100%" }}
                    onChange={(nextRange) => {
                      const next = nextRange as [Dayjs | null, Dayjs | null] | null;
                      setDateRange([next?.[0] ?? null, next?.[1] ?? null]);
                    }}
                  />
                )}
              </Space.Compact>
            </div>

            <div>
              <Typography.Text>
                <Typography.Text type="danger">*</Typography.Text>
                统计维度：
              </Typography.Text>
              <Select
                value={dimension}
                options={dimensionOptions}
                disabled={exporting}
                style={{ width: "100%", marginTop: 8 }}
                onChange={setDimension}
              />
            </div>
          </div>

          <div>
            <Typography.Title level={5} style={{ marginBottom: 14 }}>
              表头选择
            </Typography.Title>

            <div
              style={{
                display: "grid",
                gap: 12,
              }}
            >
              {exportColumnGroups.map((group) => {
                const groupKeys = group.fields.map((field) => field.key);
                const checkedCount = groupKeys.filter((key) => selectedColumnSet.has(key)).length;
                const checked = checkedCount === groupKeys.length;
                const indeterminate = checkedCount > 0 && checkedCount < groupKeys.length;

                return (
                  <div
                    key={group.title}
                    style={{
                      border: "1px solid #edf0f5",
                      borderRadius: 10,
                      padding: "12px 14px",
                      background: "#fff",
                    }}
                  >
                    <Checkbox
                      checked={checked}
                      indeterminate={indeterminate}
                      disabled={exporting}
                      onChange={(event) => toggleGroup(group, event.target.checked)}
                    >
                      <Typography.Text strong>{group.title}</Typography.Text>
                    </Checkbox>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(6, minmax(112px, 1fr))",
                        rowGap: 12,
                        columnGap: 18,
                        marginTop: 12,
                        paddingLeft: 26,
                      }}
                    >
                      {group.fields.map((field) => (
                        <Checkbox
                          key={field.key}
                          checked={selectedColumnSet.has(field.key)}
                          disabled={exporting}
                          onChange={(event) => toggleColumn(field.key, event.target.checked)}
                        >
                          {field.label}
                        </Checkbox>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </Space>
      </Modal>
    </>
  );
}

export default OrderProfitExportModal;
