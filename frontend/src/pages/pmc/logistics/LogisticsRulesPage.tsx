/** 时效与阈值设置（8088 pmc-logistics TabSettings），挂在「PMC 设置」下（Rocky 2026-11-03：PMC 只有一个设置区域）。
 * 一期只读：显示物流各页正在用的规则值；三张表服务端分页、筛选，排序走后端白名单。8088 的通知渠道映射是示例，不展示。 */
import { QuestionCircleOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Input, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType, SorterResult } from "antd/es/table/interface";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import PageShell from "@/components/page/PageShell";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import { getRuleList, getRules, type ContractRow, type CycleRow, type FcRow, type RuleSection } from "./logisticsApi";
import { logisticsError, logisticsKey } from "./logisticsQueries";
import "./logistics.css";

const { Text } = Typography;
const REGIONS = ["美西", "美中", "美东", "待定"];


interface ListState {
  page: number;
  size: number;
  keyword: string;
  region?: string;
  sort?: string;
  order: "asc" | "desc";
}

/** One read-only rule table: server paging, keyword / region filter, whitelisted sort. */
function RuleTable<Row extends object>({ scope, section, title, extra, columns, rowKey }: {
  scope: string;
  section: RuleSection;
  title: string;
  extra: string;
  columns: ColumnsType<Row>;
  rowKey: (r: Row) => string;
}) {
  const [st, setSt] = useState<ListState>({ page: 1, size: 50, keyword: "", order: "asc" });
  const params = { page: st.page, page_size: st.size, keyword: st.keyword, region: st.region, sort: st.sort, order: st.sort ? st.order : undefined };
  const q = useQuery({
    queryKey: logisticsKey(scope, "rules", section, params),
    queryFn: ({ signal }) => getRuleList<Row>(section, params, signal),
    retry: false,
    placeholderData: keepPreviousData,
  });
  const d = q.data?.data;
  return (
    <Card size="small" title={`${title}（${d?.total ?? 0} / ${d?.summary.all ?? 0}）`} extra={<Text type="secondary">{extra}</Text>}>
      <Space wrap style={{ marginBottom: 8 }} role="search" aria-label={`${title}筛选`}>
        <Input.Search allowClear aria-label={`搜索${title}`} placeholder="关键字" style={{ width: 240 }}
          onSearch={(keyword) => setSt((s) => ({ ...s, keyword, page: 1 }))} />
        <Select allowClear aria-label={`${title}地区`} placeholder="地区" style={{ width: 110 }} value={st.region}
            options={REGIONS.map((r) => ({ value: r, label: r }))} onChange={(region) => setSt((s) => ({ ...s, region, page: 1 }))} />
      </Space>
      {q.error && <Alert type="error" showIcon message={logisticsError(q.error)} />}
      <Table<Row>
        size="small"
        rowKey={rowKey}
        loading={q.isFetching}
        dataSource={d?.items ?? []}
        columns={columns}
        onChange={(pg, _f, sorter) => {
          const s = sorter as SorterResult<Row>;
          const sort = s.order ? String(s.columnKey ?? s.field) : undefined;
          setSt((x) => ({ ...x, page: pg.current ?? 1, size: pg.pageSize ?? x.size, sort, order: s.order === "descend" ? "desc" : "asc" }));
        }}
        pagination={{ current: st.page, pageSize: st.size, total: d?.total ?? 0, showSizeChanger: true, pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS, showTotal: (n) => `共 ${n} 条` }}
      />
    </Card>
  );
}

const dayCell = (v: number | null) => v ?? <Text type="secondary">地区兜底</Text>;

export default function LogisticsRulesPage({ page, scope }: { page: NavigationPage; scope: string }) {
  const q = useQuery({ queryKey: logisticsKey(scope, "rules"), queryFn: ({ signal }) => getRules(signal), retry: false });
  const d = q.data?.data;
  return (
    <PageShell page={page} headerActions={<Button href={page.help?.helpUrl ?? "/help/pmc-logistics.html"} target="_blank" rel="noreferrer" icon={<QuestionCircleOutlined />}>帮助</Button>}>
      <div className="logi-rules">
        {q.error && <Alert type="error" showIcon message={logisticsError(q.error)} style={{ marginBottom: 12 }} />}
        {d && <Alert type="info" showIcon style={{ marginBottom: 12 }} message={`数据日 ${d.today} · ${d.edit_hint}`} />}
        <Card size="small" title="全局阈值" loading={q.isLoading}>
          <Descriptions size="small" bordered column={1} items={(d?.thresholds ?? []).map((t) => ({
            key: t.key, label: t.label, children: <b>{t.value} {t.unit}</b>,
          }))} />
          <p style={{ marginTop: 8 }}>
            <Text type="secondary">无任何轨迹时的兜底（发货日 + 目的仓地区天数）：</Text>
            {Object.entries(d?.region_total ?? {}).map(([k, v]) => <Tag key={k} bordered={false}>{k} {v} 天</Tag>)}
          </p>
        </Card>
        <RuleTable<CycleRow> scope={scope} section="cycles" title="渠道分段时效" extra="提货→开船 / 开船→到港 / 到港→到货；未单独设的渠道按目的仓地区兜底"
          rowKey={(c) => c.channel_id} columns={[
            { title: "物流商", dataIndex: "provider", key: "provider", width: 160, sorter: true },
            { title: "渠道", dataIndex: "channel", key: "channel", width: 260, sorter: true, render: (_, c) => <span>{c.channel || "—"}<br /><Text type="secondary">ID {c.channel_id} · {c.method || "—"}</Text></span> },
            { title: "可去地区", width: 160, render: (_, c) => c.regions.map((r) => <Tag key={r} bordered={false}>{r}</Tag>) },
            { title: "提货→开船（天）", dataIndex: "toSail", key: "toSail", width: 130, sorter: true, render: dayCell },
            { title: "开船→到港（天）", dataIndex: "voyage", key: "voyage", width: 130, sorter: true, render: dayCell },
            { title: "到港→到货（天）", dataIndex: "days", key: "days", width: 130, sorter: true, render: dayCell },
            { title: "使用中发货单", dataIndex: "sps", key: "sps", width: 110, align: "right", sorter: true },
          ]} />
        <RuleTable<ContractRow> scope={scope} section="contracts" title="合同时效" extra="物流商 × 渠道 × 目的地区 · 提货次日到签收的约定天数"
          rowKey={(c) => `${c.provider_id}|${c.channel_id}|${c.region}`} columns={[
            { title: "物流商", dataIndex: "provider", key: "provider", width: 180, sorter: true },
            { title: "渠道", dataIndex: "channel", key: "channel", width: 260, sorter: true, render: (_, c) => <span>{c.channel || "—"}<br /><Text type="secondary">ID {c.channel_id}</Text></span> },
            { title: "目的地区", dataIndex: "region", key: "region", width: 100, sorter: true },
            { title: "合同时效（天）", dataIndex: "days", key: "days", width: 130, align: "right", sorter: true },
            { title: "提前提醒（天）", dataIndex: "remind", key: "remind", width: 130, align: "right", sorter: true },
            { title: "使用中发货单", dataIndex: "sps", key: "sps", width: 110, align: "right", sorter: true },
          ]} />
        <RuleTable<FcRow> scope={scope} section="fcs" title="目的仓 → 地区" extra="与 WFS 共用；来自领星货件地址"
          rowKey={(f) => f.fc} columns={[
            { title: "仓库代码", dataIndex: "fc", key: "fc", width: 100, sorter: true },
            { title: "地址", dataIndex: "addr" },
            { title: "城市 / 州", key: "state", width: 200, sorter: true, render: (_, f) => `${f.city}, ${f.state}` },
            { title: "邮编", dataIndex: "zip", width: 90 },
            { title: "地区", dataIndex: "region", key: "region", width: 90, sorter: true, render: (v: string) => <Tag bordered={false}>{v}</Tag> },
            { title: "发货单数", dataIndex: "n", key: "n", width: 90, align: "right", sorter: true },
          ]} />
      </div>
    </PageShell>
  );
}
