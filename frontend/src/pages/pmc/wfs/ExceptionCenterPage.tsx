/** M1: durable exception cases; rule engine and Lingxing facts stubbed. */
import { Alert, Checkbox, Select, Tag } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import ManagementStatCards from "@/components/report-table/ManagementStatCards";
import type { NavigationPage } from "@/config/navigation";
import ExceptionCenterDrawer from "./ExceptionCenterDrawer";
import WfsQueryPage from "./WfsQueryPage";
import { exceptionError, exceptionOptions, exceptionSummary, listCases } from "./exceptionCenterApi";
import type { ExceptionFilters, ExceptionRow, RuleFamily } from "./exceptionCenterTypes";
import "./PendingPackingPage.css";

const initialFilters = (): ExceptionFilters => ({
  keyword: "",
  keyword_field: "shipment",
  only_test: false,
  due_soon: false,
});

const ruleOptions: { value: RuleFamily; label: string }[] = [
  { value: "create_long_unshipped", label: "创建长期未发货" },
  { value: "arrival_overdue", label: "超过预计到仓时间" },
  { value: "arrival_no_receiving", label: "到仓后长时间未收货" },
  { value: "receiving_incomplete", label: "收货长期未完成" },
  { value: "closed_shortage_damage", label: "关闭后短少或破损" },
  { value: "appeal_deadline", label: "申诉临期提醒" },
];

const statusOptions = [
  { value: "OPEN", label: "待处理" },
  { value: "IN_PROGRESS", label: "处理中" },
  { value: "WAITING_EXTERNAL", label: "待外部反馈" },
  { value: "RESOLVED", label: "已解决" },
  { value: "CLOSED", label: "已关闭" },
];

const severityTone: Record<string, string> = { HIGH: "error", MEDIUM: "warning", LOW: "default" };
const time = (v?: string | null) =>
  v ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Taipei", dateStyle: "short" }).format(new Date(v)) : "—";

export default function ExceptionCenterPage({ page, scope = "anonymous" }: { page: NavigationPage; scope?: string }) {
  const [filters, setFilters] = useState(initialFilters);
  const [pagination, setPagination] = useState({ page: 1, size: 20 });
  const [drawerId, setDrawerId] = useState<string>();
  const [searchTick, setSearchTick] = useState(0);
  const base = useMemo(() => ["wfs-exception-center", scope], [scope]);
  const list = useQuery({
    queryKey: [...base, "list", filters, pagination, searchTick],
    queryFn: ({ signal }) => listCases(filters, pagination.page, pagination.size, signal),
    retry: false,
  });
  const summary = useQuery({
    queryKey: [...base, "summary", filters, searchTick],
    queryFn: ({ signal }) => exceptionSummary(filters, signal),
    retry: false,
  });
  const options = useQuery({
    queryKey: [...base, "options"],
    queryFn: ({ signal }) => exceptionOptions(signal),
    retry: false,
  });
  const rows = list.data?.data.items ?? [];
  const total = list.data?.data.total ?? 0;
  const stats = summary.data?.data;
  const loadError = list.error ?? summary.error;
  const commitFilters = (next: ExceptionFilters, search = false) => {
    setFilters(next);
    setPagination((p) => ({ ...p, page: 1 }));
    if (search) setSearchTick((t) => t + 1);
  };

  const columns: ProColumns<ExceptionRow>[] = [
    { title: "货件号", dataIndex: "shipment_id", width: 150 },
    { title: "异常情况", dataIndex: "rule_label", width: 200 },
    { title: "店铺", dataIndex: "store_name", width: 180, render: (_, r) => r.store_name ?? r.store_id },
    { title: "Item / MSKU", width: 160, render: (_, r) => `${r.item_id ?? "—"} / ${r.msku ?? "—"}` },
    { title: "最早发现", dataIndex: "first_detected_at", width: 120, render: (_, r) => time(r.first_detected_at) },
    {
      title: "状态",
      dataIndex: "status_label",
      width: 110,
      render: (_, r) => <Tag>{r.status_label}</Tag>,
    },
    { title: "负责人", dataIndex: "assignee_user_id", width: 120, render: (v) => v ?? "—" },
    {
      title: "严重度",
      dataIndex: "severity",
      width: 90,
      render: (_, r) => <Tag color={severityTone[r.severity]}>{r.severity}</Tag>,
    },
    { title: "期限", dataIndex: "due_at", width: 120, render: (_, r) => (r.due_at ? time(r.due_at) : "待核实") },
    { title: "差异", dataIndex: "qty_variance", width: 80, render: (v) => (v == null ? "—" : v) },
    { title: "异常说明", dataIndex: "summary", width: 280, ellipsis: true },
  ];

  return (
    <>
      <WfsQueryPage
        page={page}
        title={`异常货件（${stats?.open_shipments ?? total} 个未结案货件 / ${total} 条案件）`}
        tableLabel="异常中心表格"
        emptyText="当前条件下暂无异常货件"
        searchAriaLabel="搜索异常中心"
        inputAriaLabel="搜索异常中心关键字"
        inputPlaceholder="货件号 / PK / 说明 / 平台案件号"
        typeAriaLabel="异常中心搜索类型"
        typeOptions={[
          { value: "shipment", label: "货件号" },
          { value: "pk", label: "PK" },
          { value: "summary", label: "说明" },
          { value: "platform_case", label: "平台案件号" },
        ]}
        searchType={filters.keyword_field}
        scrollX={1680}
        loading={list.isFetching}
        loadingLabel="正在加载异常中心，请稍候"
        keyword={filters.keyword}
        rows={rows}
        total={total}
        page={pagination.page}
        pageSize={pagination.size}
        onPageChange={(page, size) => setPagination({ page, size })}
        onRowClick={(row) => setDrawerId(row.id)}
        onSearch={(keyword, searchField) =>
          commitFilters({ ...filters, keyword, keyword_field: searchField as ExceptionFilters["keyword_field"] }, true)
        }
        onReset={() => {
          commitFilters(initialFilters(), true);
          setPagination({ page: 1, size: 20 });
        }}
        aboveToolbar={
          <>
            {loadError && (
              <Alert type="error" showIcon message={exceptionError(loadError)} style={{ marginBottom: 12 }} />
            )}
            <ManagementStatCards
              ariaLabel="WFS异常中心统计"
              cards={[
                { key: "ship", title: "未结案货件", value: stats?.open_shipments ?? "—", unit: "个", tone: "warning", icon: <span>件</span>, subtitle: "去重货件数" },
                { key: "case", title: "未结案件", value: stats?.open_cases ?? "—", unit: "条", tone: "normal", icon: <span>案</span>, subtitle: "含处理中/待外部反馈" },
                { key: "due", title: "临期案件", value: stats?.due_soon_cases ?? "—", unit: "条", tone: "danger", icon: <span>期</span>, subtitle: "7 天内且未结案" },
              ]}
              activeKey=""
              onCardClick={() => undefined}
            />
          </>
        }
        filters={
          <>
            <Select
              allowClear
              aria-label="异常情况"
              className="report-filter-select"
              placeholder="全部情况"
              style={{ width: 200 }}
              value={filters.rule_family}
              onChange={(v) => commitFilters({ ...filters, rule_family: v }, true)}
              options={ruleOptions}
            />
            <Select
              allowClear
              aria-label="异常状态"
              className="report-filter-select"
              placeholder="异常状态"
              style={{ width: 130 }}
              value={filters.status}
              onChange={(v) => commitFilters({ ...filters, status: v }, true)}
              options={statusOptions}
            />
            <Select
              allowClear
              showSearch
              aria-label="店铺"
              className="report-filter-select"
              placeholder="全部店铺"
              style={{ width: 220 }}
              value={filters.store_id}
              onChange={(v) => commitFilters({ ...filters, store_id: v }, true)}
              options={options.data?.data.stores ?? []}
            />
            <Select
              allowClear
              aria-label="负责人"
              className="report-filter-select"
              placeholder="负责人"
              style={{ width: 140 }}
              value={filters.assignee_user_id}
              onChange={(v) => commitFilters({ ...filters, assignee_user_id: v }, true)}
              options={(options.data?.data.assignees ?? []).map((v) => ({ value: v, label: v }))}
            />
            <Select
              allowClear
              aria-label="严重度"
              className="report-filter-select"
              placeholder="严重度"
              style={{ width: 110 }}
              value={filters.severity}
              onChange={(v) => commitFilters({ ...filters, severity: v }, true)}
              options={[
                { value: "HIGH", label: "高" },
                { value: "MEDIUM", label: "中" },
                { value: "LOW", label: "低" },
              ]}
            />
            <Checkbox
              checked={filters.due_soon}
              onChange={(e) => commitFilters({ ...filters, due_soon: e.target.checked }, true)}
            >
              仅临期
            </Checkbox>
            <Checkbox
              checked={filters.only_test}
              onChange={(e) => commitFilters({ ...filters, only_test: e.target.checked }, true)}
            >
              仅测试
            </Checkbox>
          </>
        }
        columns={columns}
      />
      {drawerId && (
        <ExceptionCenterDrawer caseId={drawerId} scope={scope} onClose={() => setDrawerId(undefined)} />
      )}
    </>
  );
}
