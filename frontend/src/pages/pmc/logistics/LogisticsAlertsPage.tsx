/** 物流 异常与提醒（8088 pmc-logistics TabAlerts），挂在「PMC 设置」下，版式与「设置 → 业务配置中心」一致
 * （Rocky 2026-11-04：PMC 各板块的异常提醒都按系统已有方案框架做，先放 PMC 设置）：
 * 头部卡片 → 子页签（异常清单 / 提醒规则 / 通知与口径说明）→ 统计卡 → 异常类型分类按钮 → 列表卡片。
 * 一行一条异常，筛选 / 分页在服务端。8088 的「处理状态 / 负责人 / 记录 / 通知」是演示内存态，一期只读不做（PRP #298）。 */
import { AlertOutlined, BellOutlined, FileSearchOutlined, QuestionCircleOutlined, ReloadOutlined, SettingOutlined, WarningOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Empty, Input, Select, Space, Statistic, Table, Tabs, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import PageShell from "@/components/page/PageShell";
import { REPORT_TABLE_PAGE_SIZE_OPTIONS } from "@/components/report-table/pagination";
import type { NavigationPage } from "@/config/navigation";
import "@/pages/settings/BusinessConfigPage.css";
import LogisticsDrawer from "./LogisticsDrawer";
import { getAlerts, getRules, type AlertRow, type Sev } from "./logisticsApi";
import { SP_SEARCH_TYPES, type SpFilters } from "./logisticsFormat";
import { PAGE_SIZE, logisticsError, logisticsKey, useLogisticsOptions } from "./logisticsQueries";
import { SevTag, SpFilterSelects, StageTag } from "./logisticsShared";
import "./logistics.css";

const { Text } = Typography;

type Section = "list" | "rules" | "notes";

interface Filters extends SpFilters {
  type?: string;
  sev?: Sev;
}

const initial = (): Filters => ({ keyword: "", field: "sp" });

/** 异常类型口径（与 backend rules.py enrich_sp 一致；N 天类阈值见「提醒规则」）。 */
const TYPE_RULES: { type: string; sev: string; rule: string }[] = [
  { type: "已超合同时效", sev: "高", rule: "未签收，已用天数超过 物流商 × 渠道 × 目的地区 的合同时效；可索赔 = 超期天数 × 计费重 × 每 kg·天 赔付" },
  { type: "签收已超时效（可索赔）", sev: "中", rule: "已签收，但签收日晚于合同截止日" },
  { type: "即将超时", sev: "中", rule: "未签收，距合同截止剩余天数 ≤ 合同里的提前提醒天数（没设按全局「即将超时提醒」）" },
  { type: "渠道与目的地区不符", sev: "中", rule: "发货单的目的仓地区不在该渠道可去的地区里" },
  { type: "物流已签收 WFS 未收货", sev: "高 / 中", rule: "物流商已签收、WFS 货件收货数仍为 0；Walmart 侧已看到签收或 Receipt 时降为中" },
  { type: "物流已签收 Walmart 未签收", sev: "高", rule: "物流签收后超过「物流签收后 Walmart 未签收」天数，Walmart 仍没有签收" },
  { type: "Walmart 签收滞后于物流到货", sev: "中", rule: "Walmart 签收日晚于物流签收日，且相差超过上述天数" },
  { type: "Walmart 已收货 物流未显示派送", sev: "低", rule: "Walmart 已开始收货，物流商轨迹还没有签收" },
  { type: "一单多运单号（待核实）", sev: "低", rule: "一张发货单填了多个运单号" },
  { type: "收货差异（超缓冲期）", sev: "高 / 中", rule: "货件已 Closed，申报 ≠ 实收，且 Closed 超过收货差异缓冲天数；差异 ≥ 20 件为高" },
  { type: "收货差异（观察期）", sev: "低", rule: "同上，但 Closed 还在缓冲期内" },
  { type: "实际费用未录入", sev: "低", rule: "已发货超过「费用未录入」天数，领星运费仍为 0" },
  { type: "预计开船缺失", sev: "低", rule: "已发货超过「时间缺失」天数，没有预计 / 实际开船" },
  { type: "预计到港缺失", sev: "低", rule: "已发货超过「时间缺失」天数，没有预计到港" },
  { type: "运单号缺失", sev: "低", rule: "已发货，领星发货单没填运单号" },
  { type: "未关联 WFS 货件", sev: "低", rule: "已发货，发货单没有关联 WFS 货件" },
  { type: "无合同时效", sev: "低", rule: "物流商 × 渠道 × 目的地区 没有合同时效" },
];

export default function LogisticsAlertsPage({ page, scope }: { page: NavigationPage; scope: string }) {
  const [section, setSection] = useState<Section>("list");
  const [filters, setFilters] = useState(initial);
  const [draft, setDraft] = useState("");
  const [pg, setPg] = useState({ page: 1, size: PAGE_SIZE });
  const [open, setOpen] = useState<string>();
  const opts = useLogisticsOptions(scope);
  const options = opts.data?.data;
  const params = { ...filters, page: pg.page, page_size: pg.size };
  const q = useQuery({
    queryKey: logisticsKey(scope, "alerts", params),
    queryFn: ({ signal }) => getAlerts(params, signal),
    retry: false,
    placeholderData: keepPreviousData,
  });
  const rules = useQuery({
    queryKey: logisticsKey(scope, "rules"),
    queryFn: ({ signal }) => getRules(signal),
    retry: false,
    enabled: section === "rules",
  });
  const data = q.data?.data;
  const sum = data?.summary;
  const commit = (next: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...next }));
    setPg((p) => ({ ...p, page: 1 }));
  };
  const types = options?.alert_types ?? TYPE_RULES.map((t) => t.type);
  const error = opts.error ?? q.error;

  const columns: ColumnsType<AlertRow> = [
    { title: "严重度", width: 80, render: (_, e) => <SevTag sev={e.sev} /> },
    { title: "类型", width: 200, render: (_, e) => <b>{e.type}</b> },
    { title: "发货单", width: 170, render: (_, e) => <a onClick={() => setOpen(e.code)}>{e.code}</a> },
    { title: "阶段", width: 110, render: (_, e) => <StageTag stage={e.stage} /> },
    { title: "物流商 · 渠道 · 地区", width: 220, render: (_, e) => <span>{e.provider}<br /><Text type="secondary">{e.channel} · {e.fc} {e.region}</Text></span> },
    { title: "店铺", width: 200, render: (_, e) => e.stores.join(" / ") || "—" },
    { title: "说明", render: (_, e) => <span className="logi-wrap">{e.desc}</span> },
    { title: "发现", width: 110, render: (_, e) => e.since || "—" },
  ];

  const helpUrl = page.help?.helpUrl ?? "/help/pmc-logistics.html";
  return (
    <PageShell page={page}>
      <div className="business-config logi-alerts">
        <section className="business-config__header">
          <div className="business-config__heading">
            <span className="business-config__eyebrow">PMC SETTINGS</span>
            <h1>物流 异常与提醒</h1>
            <p>按发货单逐条检查合同时效、物流签收、Walmart 收货与数据缺失；数据日 {options?.today ?? "—"}，只读</p>
          </div>
          <Space>
            <Button icon={<ReloadOutlined />} loading={q.isFetching} onClick={() => { void q.refetch(); void opts.refetch(); }}>刷新数据</Button>
            <Button icon={<QuestionCircleOutlined />} href={helpUrl} target="_blank" rel="noreferrer">帮助</Button>
          </Space>
        </section>
        <div className="business-config__tabs">
          <Tabs activeKey={section} onChange={(key) => setSection(key as Section)} items={[
            { key: "list", label: <span><AlertOutlined /> 异常清单</span> },
            { key: "rules", label: <span><SettingOutlined /> 提醒规则</span> },
            { key: "notes", label: <span><BellOutlined /> 通知与口径说明</span> },
          ]} />
        </div>

        {section === "list" && (
          <div className="business-config__body">
            {error && <Alert type="error" showIcon message={logisticsError(error)} />}
            <div className="business-config__stats">
              <Card><Statistic title="异常总数" value={sum?.all ?? 0} suffix="条" prefix={<WarningOutlined />} loading={q.isLoading} /><span>当前数据范围内全部发货单</span></Card>
              <Card><Statistic title="涉及发货单" value={sum?.sps ?? 0} suffix="张" prefix={<FileSearchOutlined />} loading={q.isLoading} /><span>至少有一条异常的发货单</span></Card>
              <Card><Statistic title="高严重度" value={sum?.sevs?.high ?? 0} suffix="条" valueStyle={{ color: "var(--ant-color-error, #cf1322)" }} loading={q.isLoading} /><span>已超时效 / 签收未收货等，优先处理</span></Card>
              <Card><Statistic title="中 / 低" value={`${sum?.sevs?.mid ?? 0} / ${sum?.sevs?.low ?? 0}`} loading={q.isLoading} /><span>即将超时、差异观察期、数据缺失</span></Card>
            </div>

            <div className="business-config__categories" role="group" aria-label="异常类型">
              <strong>异常类型</strong>
              <div className="business-config__category-buttons">
                <Button size="small" type={!filters.type ? "primary" : "default"} ghost={!filters.type} onClick={() => commit({ type: undefined })}>
                  全部异常<span className="business-config__count">{sum?.all ?? 0}</span>
                </Button>
                {types.map((t) => (
                  <Button key={t} size="small" type={filters.type === t ? "primary" : "default"} ghost={filters.type === t}
                    onClick={() => commit({ type: filters.type === t ? undefined : t })}>
                    {t}<span className="business-config__count">{sum?.types[t] ?? 0}</span>
                  </Button>
                ))}
              </div>
            </div>

            <Card className="business-config__list-card" title={filters.type ?? "全部异常"}
              extra={<span className="business-config__muted">{data?.total ?? 0} 条</span>}>
              <div className="business-config__filters" role="search" aria-label="物流异常筛选">
                <Space.Compact>
                  <Select aria-label="物流异常搜索类型" value={filters.field} style={{ width: 130 }} options={SP_SEARCH_TYPES}
                    onChange={(field) => { if (draft) commit({ field }); else setFilters((f) => ({ ...f, field })); }} />
                  <Input.Search aria-label="搜索物流异常关键字" allowClear placeholder="发货单号 / 货件 / 运单号 / SKU" className="business-config__search"
                    value={draft} onChange={(e) => setDraft(e.target.value)} onSearch={(keyword) => commit({ keyword: keyword.trim() })} />
                </Space.Compact>
                <Select allowClear aria-label="严重度" className="business-config__status-filter" placeholder="全部等级" style={{ width: 110 }}
                  value={filters.sev} options={[{ value: "high", label: "高" }, { value: "mid", label: "中" }, { value: "low", label: "低" }]} onChange={(sev) => commit({ sev })} />
                <SpFilterSelects options={options} filters={filters} commit={commit} />
                <span className="business-config__filter-spacer" />
                <Button onClick={() => { setFilters(initial()); setDraft(""); setPg({ page: 1, size: PAGE_SIZE }); }}>重置</Button>
              </div>
              <Table<AlertRow>
                aria-label="物流异常表格"
                rowKey="id"
                size="small"
                loading={q.isFetching}
                dataSource={data?.items ?? []}
                columns={columns}
                scroll={{ x: 1400 }}
                locale={{ emptyText: <Empty description={q.isFetching ? "正在加载" : "当前条件下暂无异常"} /> }}
                onRow={(e) => ({ onClick: () => setOpen(e.code) })}
                pagination={{
                  current: pg.page, pageSize: pg.size, total: data?.total ?? 0, showSizeChanger: true,
                  pageSizeOptions: REPORT_TABLE_PAGE_SIZE_OPTIONS, showTotal: (n) => `共 ${n} 条`,
                  onChange: (p, size) => setPg({ page: size !== pg.size ? 1 : p, size }),
                }}
              />
              <div className="business-config__list-footer">
                共 {data?.total ?? 0} 条 / 全部 {sum?.all ?? 0} 条 · 只读：处理状态、负责人、处理记录和通知待上线；点一行看发货单详情
              </div>
            </Card>
          </div>
        )}

        {section === "rules" && (
          <div className="business-config__body">
            {rules.error && <Alert type="error" showIcon message={logisticsError(rules.error)} />}
            <Card title="提醒阈值" className="business-config__list-card" loading={rules.isLoading}
              extra={<Text type="secondary">{rules.data?.data.edit_hint ?? "一期只读"}</Text>}>
              <Descriptions size="small" bordered column={2} items={(rules.data?.data.thresholds ?? []).map((t) => ({
                key: t.key, label: t.label, children: <b>{t.value} {t.unit}</b>,
              }))} />
              <p style={{ marginTop: 8 }}>
                <Text type="secondary">合同时效、渠道分段时效、目的仓地区见「物流 时效与阈值设置」。</Text>
              </p>
            </Card>
            <Card title="异常类型与触发条件" className="business-config__list-card">
              <Table size="small" rowKey="type" pagination={false} dataSource={TYPE_RULES} columns={[
                { title: "异常类型", dataIndex: "type", width: 220, render: (v: string) => <b>{v}</b> },
                { title: "严重度", dataIndex: "sev", width: 90 },
                { title: "触发条件", dataIndex: "rule" },
                { title: "当前条数", width: 100, align: "right", render: (_: unknown, t) => sum?.types[t.type] ?? 0 },
              ]} />
            </Card>
          </div>
        )}

        {section === "notes" && (
          <div className="business-config__body">
            <Alert type="info" showIcon message="通知暂未上线" description="一期只在页面上显示异常，不发飞书 / 邮件通知；8088 的通知渠道映射是演示数据，没有迁过来。通知规则上线后在这里配置。" />
            <Card title="口径说明" className="business-config__list-card">
              <ul className="logi-notes">
                <li>数据日 = 计算用的“今天”（8088 规则按数据日计算），当前 {options?.today ?? "—"}；数据来自已校验的领星发货单、物流商运单文件（目前只有众壹）和 Walmart 货件 / Receipt 文件，不调用任何接口。</li>
                <li>合同时效从提货次日起算；提货 = 物流商「货物进入操作中心」，没有则用领星实际发货 / 发货时间。</li>
                <li>到货（物流签收）= 物流商「签收完成」；Walmart 签收 = 货件 actualDeliveryDate，没有则用最早 Receipt。</li>
                <li>收货差异只看已 Closed 的货件：申报数与实收数不等时提醒，Closed 未满缓冲天数算观察期。</li>
                <li>一张发货单可以同时有多条异常；统计卡和分类计数不受筛选影响，列表条数随筛选变化。</li>
                <li><Tag bordered={false}>高</Tag>先处理，<Tag bordered={false}>中</Tag>跟进，<Tag bordered={false}>低</Tag>多为数据缺失，补领星数据后自动消失。</li>
              </ul>
            </Card>
          </div>
        )}
      </div>
      {open && (
        <LogisticsDrawer
          code={open}
          scope={scope}
          buffer={options?.rules.wm_receive_buffer ?? 10}
          deliveredNotSigned={options?.rules.delivered_not_signed ?? 2}
          onClose={() => setOpen(undefined)}
        />
      )}
    </PageShell>
  );
}
