/**
 * WFS 异常与提醒 (PMC 设置). Rocky 2026-11-04: every PMC 异常提醒 page follows the existing
 * 设置 → 业务配置中心 frame (header card, sub-tabs, stat cards, category buttons, list card) and
 * lives under PMC 设置; the logistics alert page uses the same frame. Reuses the
 * BusinessConfigPage class names; the rule list stays server-side filtered / sorted / paged and
 * rule saving stays whole-version (PRP pmc-wfs-settings §5).
 */
import {
  BellOutlined, CheckCircleOutlined, ExclamationCircleOutlined, HistoryOutlined,
  ReloadOutlined, UnorderedListOutlined,
} from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Empty, Pagination, Select, Space, Statistic, Tabs, Tag, message } from "antd";
import { useState } from "react";
import PageShell from "@/components/page/PageShell";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ReportTableShell from "@/components/report-table/ReportTableShell";
import ResetButton from "@/components/report-table/ResetButton";
import { StatusTagCell } from "@/components/report-table/cells";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import "@/pages/settings/BusinessConfigPage.css";
import {
  RULE_CATEGORIES, RULE_SORTS, listRuleRows, settingsError, type RuleCategory, type RuleRowItem,
} from "../settingsApi";
import { RuleHistoryTables } from "./RuleHistoryDrawer";
import RuleVersionEditor from "./RuleVersionEditor";
import { SAMPLE_TAG, settingsAccess, type SectionProps } from "./settingsShared";
import { sortFromTable, useSettingsListState } from "./useSettingsListState";
import "../WfsSettingsPage.css";

export type AlertCenterTab = "rules" | "notes" | "history";
type RuleSort = (typeof RULE_SORTS)[number];
type Row = RuleRowItem & { id: string } & Record<string, unknown>;

export const ALERT_CENTER_TITLE = "WFS 异常与提醒";
const categoryLabel = (key?: RuleCategory) => RULE_CATEGORIES.find((c) => c.key === key)?.label;

const NOTES = [
  { key: "notify", label: "通知", children: "通知未接入：本期只保存「通知对象」文字，不发消息。" },
  { key: "buffer", label: "上架缓冲天数", children: "上架缓冲天数（10 天）引用「自动补货」的规则，这里只读显示，修改请到自动补货设置。" },
  { key: "version", label: "规则版本", children: "规则改动保存为新版本，从生效日起使用；生效日之前的看板与异常仍按旧版本计算。" },
  { key: "sample", label: "示例阈值", children: `标「${SAMPLE_TAG}」的阈值是 8088 示例值，业务确认后改为正式值。` },
  { key: "log", label: "修改留痕", children: "地区与默认值的修改立即生效，每次修改都要填原因并留修改记录。" },
  { key: "source", label: "外部系统", children: "PMC 设置不调用领星，也不写入 Walmart。" },
];

export default function WfsAlertCenter({ page, scope, permissions, initialTab = "rules" }: SectionProps & { initialTab?: AlertCenterTab }) {
  const qc = useQueryClient();
  const { canManage, writeHint } = settingsAccess(page, permissions);
  const [tab, setTab] = useState<AlertCenterTab>(initialTab);
  const [editorOpen, setEditorOpen] = useState(false);
  const list = useSettingsListState<{ region: string; decided: string; category: RuleCategory }, RuleSort>("row_no");
  const query = {
    ...list.query,
    region: list.filters.region,
    category: list.filters.category,
    decided: list.filters.decided === undefined ? undefined : list.filters.decided === "true",
  };
  const rows = useQuery({
    queryKey: ["pmc-settings", scope, "rule-rows", query],
    queryFn: ({ signal }) => listRuleRows(query, signal),
    retry: false,
  });
  const data = rows.error ? undefined : rows.data;
  const sortOrder = (key: RuleSort) => (list.sort.by === key ? (list.sort.order === "desc" ? "descend" : "ascend") : null);
  const category = list.filters.category;

  const columns: ProColumns<Row>[] = [
    { title: "节点", key: "node", width: 300, fixed: "left", sorter: true, sortOrder: sortOrder("node"), render: (_, r) => r.node },
    { title: "分类", key: "category", width: 100, render: (_, r) => <Tag>{categoryLabel(r.category) ?? "其他"}</Tag> },
    {
      title: "阈值状态", key: "decided", width: 110,
      render: (_, r) => (r.decided ? <StatusTagCell label="已确认" color="success" /> : <StatusTagCell label={SAMPLE_TAG} color="warning" />),
    },
    { title: "地区", key: "region", width: 80, render: (_, r) => r.region || "—" },
    { title: "承运商 / 渠道", key: "carrier", width: 130, render: (_, r) => `${r.carrier || "—"} / ${r.channel || "—"}` },
    { title: "天数", key: "days", width: 80, align: "right", sorter: true, sortOrder: sortOrder("days"), render: (_, r) => r.days },
    { title: "提前提醒", key: "remind_days", width: 90, align: "right", render: (_, r) => r.remind_days },
    {
      title: "生效日", key: "row_effective_date", width: 110, sorter: true, sortOrder: sortOrder("row_effective_date"),
      render: (_, r) => r.row_effective_date,
    },
    { title: "通知对象", key: "notify", width: 180, render: (_, r) => r.notify || "—" },
    { title: "备注", key: "remark", width: 300, render: (_, r) => r.remark || "—" },
  ];

  const stats = (
    <div className="business-config__stats">
      <Card><Statistic title="规则总数" value={data?.total_rows ?? "—"} prefix={<UnorderedListOutlined />} loading={rows.isLoading} /><span>当前生效版本的全部规则</span></Card>
      <Card><Statistic title="已确认阈值" value={data ? data.total_rows - data.sample_rows : "—"} prefix={<CheckCircleOutlined />} loading={rows.isLoading} /><span>业务已确认的正式值</span></Card>
      <Card><Statistic title={SAMPLE_TAG} value={data?.sample_rows ?? "—"} prefix={<ExclamationCircleOutlined />} loading={rows.isLoading} /><span>按 8088 示例阈值执行</span></Card>
      <Card><Statistic title="当前版本" value={data ? `v${data.version.version_no}` : "—"} prefix={<HistoryOutlined />} loading={rows.isLoading} /><span>{data ? `生效日 ${data.version.effective_date}` : "版本按生效日切换"}</span></Card>
    </div>
  );

  const categories = (
    <div className="business-config__categories" role="group" aria-label="规则分类">
      <strong>规则分类</strong>
      <div className="business-config__category-buttons">
        {[{ key: undefined, label: "全部规则" }, ...RULE_CATEGORIES].map((c) => {
          const active = category === c.key;
          const count = c.key ? data?.category_counts[c.key] : data?.total_rows;
          return (
            <Button key={c.key ?? "all"} size="small" type={active ? "primary" : "default"} ghost={active}
              aria-pressed={active} onClick={() => list.setFilter("category", c.key)}>
              {c.label}<span className="business-config__count">{count ?? "—"}</span>
            </Button>
          );
        })}
      </div>
    </div>
  );

  const ruleList = (
    <Card className="business-config__list-card" title={categoryLabel(category) ?? "全部规则"}
      extra={<span className="business-config__muted">{data ? `${data.total} 条` : ""}</span>}>
      <div className="business-config__filters" role="search" aria-label="异常与提醒规则筛选">
        <CommittedSearch
          key={`${list.search.field}:${list.search.keyword}`}
          className="pmc-alert-center__search"
          typeAriaLabel="规则搜索类型"
          typeValue={list.search.field}
          typeOptions={[{ value: "all", label: "全部" }, { value: "node", label: "节点" }, { value: "remark", label: "备注" }, { value: "notify", label: "通知对象" }]}
          inputAriaLabel="搜索规则关键字"
          inputValue={list.search.keyword}
          inputPlaceholder="节点 / 备注 / 通知对象"
          searchAriaLabel="搜索规则"
          onCommit={({ keyword, searchField }) => list.setSearch({ keyword: keyword.trim(), field: searchField })}
        />
        <Select allowClear aria-label="地区" className="business-config__status-filter" placeholder="全部地区"
          value={list.filters.region} onChange={(v?: string) => list.setFilter("region", v)}
          options={(data?.regions ?? []).map((v) => ({ value: v, label: v }))} />
        <Select allowClear aria-label="阈值状态" className="business-config__status-filter" placeholder="全部状态"
          value={list.filters.decided} onChange={(v?: string) => list.setFilter("decided", v)}
          options={[{ value: "true", label: "已确认" }, { value: "false", label: SAMPLE_TAG }]} />
        <span className="business-config__filter-spacer" />
        <ResetButton aria-label="重置规则筛选" onClick={list.reset} />
      </div>
      {rows.error && <Alert type="error" showIcon message={settingsError(rows.error)} action={<Button size="small" onClick={() => void rows.refetch()}>重试</Button>} />}
      <div className="pmc-alert-center__table-wrap">
        <ReportTableShell label="异常与提醒规则表格">
          <ProTable<Row>
            rowKey="id"
            search={false}
            options={false}
            toolBarRender={false}
            tableAlertRender={false}
            size="small"
            bordered
            loading={rows.isFetching}
            columns={columns}
            dataSource={(data?.items ?? []).map((r, i) => ({ ...r, id: `${r.rule_key ?? "row"}-${i}` }))}
            scroll={{ x: 1480, y: "100%" }}
            pagination={false}
            onChange={(_, __, sorter, extra) => {
              if (extra.action !== "sort") return;
              const s = sortFromTable(sorter, RULE_SORTS, "row_no");
              list.setSort(s.by, s.order);
            }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={rows.error ? "数据加载失败，请查看错误提示并重试" : "当前条件下暂无规则，可重置条件查看"} /> }}
          />
          <Pagination
            className="ant-table-pagination"
            size="small"
            current={list.pagination.page}
            pageSize={list.pagination.pageSize}
            total={data?.total ?? 0}
            showSizeChanger
            showQuickJumper
            pageSizeOptions={REPORT_TABLE_PAGE_SIZE_OPTIONS}
            showTotal={(n) => `共 ${n} 条`}
            onChange={(p, size) => list.setPagination(size !== list.pagination.pageSize ? 1 : p, size)}
          />
        </ReportTableShell>
      </div>
      <div className="business-config__list-footer">规则改动保存为新版本，从生效日起使用 · 数据来自新系统数据库</div>
    </Card>
  );

  return (
    <PageShell page={page}>
      <div className="business-config pmc-alert-center">
        <section className="business-config__header">
          <div className="business-config__heading">
            <span className="business-config__eyebrow">PMC SETTINGS</span>
            <h1>{ALERT_CENTER_TITLE}</h1>
            <p>WFS 货件各节点的时效阈值、提前提醒与通知口径</p>
          </div>
          <Space wrap>
            {writeHint && <Tag>{writeHint}</Tag>}
            <Button icon={<ReloadOutlined />} onClick={() => void qc.invalidateQueries({ queryKey: ["pmc-settings", scope] })}>刷新数据</Button>
            <Button type="primary" disabled={!canManage} title={writeHint} onClick={() => setEditorOpen(true)}>编辑规则</Button>
          </Space>
        </section>
        <div className="business-config__tabs">
          <Tabs activeKey={tab} onChange={(key) => setTab(key as AlertCenterTab)} items={[
            { key: "rules", label: <span><UnorderedListOutlined /> 提醒规则</span> },
            { key: "notes", label: <span><BellOutlined /> 通知与口径说明</span> },
            { key: "history", label: <span><HistoryOutlined /> 版本与修改记录</span> },
          ]} />
        </div>
        {tab === "rules" && (
          <div className="business-config__body">
            <Alert type="info" showIcon message="规则口径"
              description={data && data.sample_rows > 0
                ? `有 ${data.sample_rows} 条规则按示例阈值执行（标「${SAMPLE_TAG}」），业务确认后改成正式值；通知本期未接入，只保存通知对象。`
                : "规则按生效日切换版本；通知本期未接入，只保存通知对象。"} />
            {stats}
            {categories}
            {ruleList}
          </div>
        )}
        {tab === "notes" && (
          <div className="business-config__body">
            <Card className="business-config__list-card" title="通知与口径说明">
              <Descriptions column={1} size="small" bordered items={NOTES} />
              <div className="business-config__list-footer">说明 · 不请求业务数据</div>
            </Card>
          </div>
        )}
        {tab === "history" && (
          <div className="business-config__body">
            <Card className="business-config__list-card" title="版本与修改记录">
              <RuleHistoryTables scope={scope} />
            </Card>
          </div>
        )}
        <RuleVersionEditor
          open={editorOpen}
          scope={scope}
          canManage={canManage}
          onClose={() => setEditorOpen(false)}
          onSaved={() => {
            void message.success("已保存为新版本");
            setEditorOpen(false);
            void qc.invalidateQueries({ queryKey: ["pmc-settings", scope] });
          }}
        />
      </div>
    </PageShell>
  );
}
