import {
  ApiOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  CloudOutlined,
  LinkOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  TableOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Drawer,
  Empty,
  Input,
  Segmented,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useCallback, useEffect, useMemo, useState } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import { fetchCurrentUser } from "@/pages/auth/authApi";
import {
  fetchDecodoConfig,
  fetchDecodoUsage,
  updateDecodoConfig,
  type DecodoConfig,
  type DecodoUsageDay,
} from "@/api/decodoApi";
import "@/pages/settings/BusinessConfigPage.css";
import BusinessConfigDraftManager from "@/pages/settings/BusinessConfigDraftManager";
import BusinessConfigServiceEditor from "@/pages/settings/BusinessConfigServiceEditor";
import { listBusinessConnectors, type BusinessConnector } from "@/api/businessConnectorsApi";
import { readBrowserDrafts, type ServiceDraft } from "@/pages/settings/businessConfigDrafts";
import { PlusOutlined } from "@ant-design/icons";
import LiveBusinessConnectors from "@/pages/settings/LiveBusinessConnectors";

type Section = "connections" | "usage" | "policies";
type Category = "all" | "crawler" | "ai" | "communication" | "bots" | "commerce" | "erp" | "logistics";
type ViewMode = "table" | "cards";
type UsageRange = 7 | 30;

const BUSINESS_CONFIG_CATEGORIES: ReadonlyArray<{ key: Category; label: string }> = [
  { key: "all", label: "全部服务" },
  { key: "crawler", label: "爬虫与代理" },
  { key: "ai", label: "AI 服务" },
  { key: "communication", label: "企业通讯" },
  { key: "bots", label: "群机器人与通知" },
  { key: "commerce", label: "电商平台" },
  { key: "erp", label: "ERP 与数据服务" },
  { key: "logistics", label: "物流与仓储" },
];

const labelDate = (date: string | null | undefined) =>
  date && dayjs(date).isValid() ? dayjs(date).format("YYYY-MM-DD HH:mm") : "—";

const decodoStatus = (config: DecodoConfig): "未配置" | "已启用" | "已停用" => {
  if (!config.configured) return "未配置";
  return config.enabled ? "已启用" : "已停用";
};

interface BusinessConfigPageProps {
  page: NavigationPage;
}

export default function BusinessConfigPage({ page }: BusinessConfigPageProps) {
  const [messageApi, messageContextHolder] = message.useMessage();
  const [section, setSection] = useState<Section>("connections");
  const [category, setCategory] = useState<Category>("all");
  const [keyword, setKeyword] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [usageRange, setUsageRange] = useState<UsageRange>(7);
  const [config, setConfig] = useState<DecodoConfig | null>(null);
  const [usageRows, setUsageRows] = useState<DecodoUsageDay[]>([]);
  const [usageToday, setUsageToday] = useState("");
  const [configLoading, setConfigLoading] = useState(true);
  const [usageLoading, setUsageLoading] = useState(true);
  const [configError, setConfigError] = useState(false);
  const [usageError, setUsageError] = useState(false);
  const [canEdit, setCanEdit] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draftAuthorization, setDraftAuthorization] = useState("");
  const [draftZip, setDraftZip] = useState("10001");
  const [draftEnabled, setDraftEnabled] = useState(false);
  const [live, setLive] = useState<BusinessConnector[]>([]);
  const [liveError, setLiveError] = useState(false);
  const [liveLoading, setLiveLoading] = useState(true);
  const [drafts, setDrafts] = useState<ServiceDraft[]>([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingLive, setEditingLive] = useState<BusinessConnector | null>(null);
  const [editingDraft, setEditingDraft] = useState<ServiceDraft | null>(null);

  const loadConfig = useCallback(async () => {
    setConfigLoading(true);
    try {
      const result = await fetchDecodoConfig();
      setConfig(result);
      setConfigError(false);
    } catch {
      setConfigError(true);
    } finally {
      setConfigLoading(false);
    }
  }, []);

  const loadUsage = useCallback(async (days: UsageRange) => {
    setUsageLoading(true);
    try {
      const result = await fetchDecodoUsage(days);
      setUsageRows(result.days);
      setUsageToday(result.today);
      setUsageError(false);
    } catch {
      setUsageRows([]);
      setUsageError(true);
    } finally {
      setUsageLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;

    void fetchDecodoConfig()
      .then((result) => {
        if (!active) return;
        setConfig(result);
        setConfigError(false);
      })
      .catch(() => {
        if (active) setConfigError(true);
      })
      .finally(() => {
        if (active) setConfigLoading(false);
      });

    void fetchCurrentUser()
      .then((user) => {
        if (active) setCanEdit(Boolean(user?.isSuperAdmin));
      })
      .catch(() => {
        if (active) setCanEdit(false);
      });

    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;

    void fetchDecodoUsage(usageRange)
      .then((result) => {
        if (!active) return;
        setUsageRows(result.days);
        setUsageToday(result.today);
        setUsageError(false);
      })
      .catch(() => {
        if (!active) return;
        setUsageRows([]);
        setUsageError(true);
      })
      .finally(() => {
        if (active) setUsageLoading(false);
      });

    return () => { active = false; };
  }, [usageRange]);

  const refreshConnectors = useCallback(async () => {
    setLiveLoading(true);
    try { setLive(await listBusinessConnectors()); setLiveError(false); }
    catch { setLiveError(true); }
    finally { setLiveLoading(false); }
    setDrafts(readBrowserDrafts().services);
  }, []);
  useEffect(() => {
    let active = true;
    void listBusinessConnectors().then((rows) => {
      if (active) { setLive(rows); setLiveError(false); }
    }).catch(() => { if (active) setLiveError(true); })
      .finally(() => { if (active) setLiveLoading(false); });
    return () => { active = false; };
  }, []);
  const openServiceEditor = (connector?: BusinessConnector, draft?: ServiceDraft) => {
    setEditingLive(connector ?? null);
    setEditingDraft(draft ?? null);
    setEditorOpen(true);
  };
  const isLocalMode = config?.mode === "local_test";
  const todayRow = useMemo(
    () => usageRows.find((row) => row.date === usageToday),
    [usageRows, usageToday],
  );
  const totalRequests = useMemo(
    () => usageRows.reduce((sum, row) => sum + row.total, 0),
    [usageRows],
  );
  const chartRows = useMemo(() => [...usageRows].reverse(), [usageRows]);
  const chartMax = Math.max(...chartRows.map((row) => row.total), 1);

  const [detailsOpen, setDetailsOpen] = useState(false);

  const openEditor = () => {
    if (!config || isLocalMode || !canEdit) return;
    setDraftZip(config.us_zip);
    setDraftEnabled(config.enabled);
    setDraftAuthorization("");
    setDrawerOpen(true);
  };

  const save = async () => {
    if (!config || !canEdit || isLocalMode || saving) return;
    if (!/^[0-9]{5}$/.test(draftZip)) {
      messageApi.error("请输入 5 位美国邮编");
      return;
    }
    if (draftEnabled && !config.configured && !draftAuthorization.trim()) {
      messageApi.error("首次启用必须填写 Decodo Basic Authorization");
      return;
    }
    setSaving(true);
    try {
      await updateDecodoConfig({
        us_zip: draftZip,
        enabled: draftEnabled,
        ...(draftAuthorization.trim() ? { authorization: draftAuthorization.trim() } : {}),
      });
      setDraftAuthorization("");
      setDrawerOpen(false);
      messageApi.success("Decodo 配置已保存；原有密钥不会回显");
      await loadConfig();
    } catch {
      messageApi.error("保存失败：请检查超级管理员权限、配置密钥或本地写入限制");
    } finally {
      setSaving(false);
    }
  };

  const goToUsage = () => {
    setSection("usage");
    setUsageRange(7);
  };

  type ServiceRow = { key: string; name: string; subtitle: string; category: Category; purpose: string; state: string; calls: string; billing: string; updated: string; connector?: BusinessConnector; draft?: ServiceDraft; decodo?: boolean };
  const rows: ServiceRow[] = [
    ...(config ? [{
      key: "decodo", name: "Decodo Scraper API", subtitle: "Decodo · 系统默认实例",
      category: "crawler" as Category, purpose: "Amazon / Walmart 商品信息采集",
      state: decodoStatus(config), calls: usageError ? "—" : String(todayRow?.total ?? 0),
      billing: "未配置计价", updated: labelDate(config.updated_at), decodo: true,
    }] : []),
    ...live.map((item): ServiceRow => ({
      key: item.id, name: item.name,
      subtitle: item.kind === "openai" ? "OpenAI · 模型服务" : "飞书 · 群机器人",
      category: item.kind === "openai" ? "ai" : "bots",
      purpose: item.kind === "openai" ? "AI 模型生成与调用" : "业务群通知推送",
      state: item.enabled ? "已启用" : "已停用", calls: "—",
      billing: item.kind === "openai" ? "按 Token 估算" : "不计费",
      updated: labelDate(item.updated_at), connector: item,
    })),
    ...drafts.map((item): ServiceRow => ({
      key: item.id, name: item.name, subtitle: item.provider + " · 配置草稿",
      category: item.category, purpose: item.purpose || "未设置用途",
      state: "草稿", calls: "—", billing: "未接入",
      updated: labelDate(item.updatedAt), draft: item,
    })),
  ];
  const filteredRows = rows.filter((item) => (
    (category === "all" || item.category === category) &&
    (statusFilter === "all" || item.state === statusFilter || (statusFilter === "未配置" && item.state === "草稿")) &&
    [item.name, item.subtitle, item.purpose].join(" ").toLowerCase().includes(keyword.toLowerCase().trim())
  ));
  const categoriesCount = (key: Category) => key === "all" ? rows.length : rows.filter((item) => item.category === key).length;
  const columns: ColumnsType<ServiceRow> = [
    { title: "服务 / 配置名称", key: "name", width: 245,
      render: (_, item) => <Space align="center">
        <span className="business-config__service-avatar">{item.decodo ? "DE" : item.category === "ai" ? "AI" : item.category === "bots" ? "飞" : "◆"}</span>
        <span><strong>{item.name}</strong><span className="business-config__subline">{item.subtitle}</span></span>
      </Space> },
    { title: "业务用途", dataIndex: "purpose" },
    { title: "连接状态", dataIndex: "state", width: 115,
      render: (value: string) => <Tag color={value === "已启用" ? "success" : value === "草稿" ? "warning" : "default"}>{value}</Tag> },
    { title: "今日调用", dataIndex: "calls", width: 95 },
    { title: "计费方式", dataIndex: "billing", width: 125 },
    { title: "最近修改", dataIndex: "updated", width: 145 },
    { title: "操作", key: "actions", width: 172, render: (_, item) => <Space size={0}>
      <Button type="link" size="small" onClick={() => item.decodo ? setDetailsOpen(true) : item.connector || item.draft ? openServiceEditor(item.connector, item.draft) : undefined}>详情</Button>
      {item.decodo && <Button type="link" size="small" onClick={goToUsage}>用量</Button>}
      {canEdit && (item.connector || item.draft || (item.decodo && !isLocalMode)) &&
        <Button type="link" size="small" onClick={() => item.decodo ? openEditor() : openServiceEditor(item.connector, item.draft)}>编辑</Button>}
    </Space> },
  ];

  return (
    <>
      {messageContextHolder}
      <PageShell page={page}>
        <div className="business-config">
          <section className="business-config__header">
            <div className="business-config__heading">
              <span className="business-config__eyebrow">INTEGRATION MANAGEMENT</span>
              <h1>业务配置中心</h1>
              <p>第三方服务统一接入、调用统计与使用策略管理</p>
            </div>
            <Space>
              <Button icon={<ReloadOutlined />} loading={configLoading || usageLoading || liveLoading}
                onClick={() => { void loadConfig(); void loadUsage(usageRange); void refreshConnectors(); }}>刷新数据</Button>
              {canEdit && <Button icon={<PlusOutlined />} type="primary" onClick={() => openServiceEditor()}>新增服务配置</Button>}
            </Space>
          </section>
          <div className="business-config__tabs">
            <Tabs activeKey={section} onChange={(key) => setSection(key as Section)} items={[
              { key: "connections", label: <span><LinkOutlined /> 服务配置</span> },
              { key: "usage", label: <span><BarChartOutlined /> 用量与费用</span> },
              { key: "policies", label: <span><SettingOutlined /> 使用策略</span> },
            ]} />
          </div>

          {section === "connections" ? (
            <div className="business-config__body">
              <div className="business-config__stats">
                <Card><Statistic title="已接入服务" value={(config ? 1 : 0) + live.length} prefix={<LinkOutlined />} /><span>实际接入的服务实例</span></Card>
                <Card><Statistic title="已启用连接" value={(config?.enabled ? 1 : 0) + live.filter((item) => item.enabled).length} prefix={<SafetyCertificateOutlined />} /><span>由后端配置状态决定</span></Card>
                <Card><Statistic title="今日总请求" value={usageError ? "—" : (todayRow?.total ?? 0)} prefix={<ApiOutlined />} loading={usageLoading} /><span>美国东部业务日期</span></Card>
                <Card><Statistic title="今日预估费用" value="未配置计价" prefix={<CloudOutlined />} /><span>不将调用次数误认为收费金额</span></Card>
              </div>

              {configError ? <Alert showIcon type="error" message="Decodo 配置读取失败" description="请检查登录、权限、后端服务及数据库版本；未读取到真实配置时不显示虚拟实例。" action={<Button size="small" onClick={() => void loadConfig()}>重试</Button>} /> : null}
              {isLocalMode ? <Alert showIcon type="info" message="当前是 Decodo 本地 SQLite 测试模式" description="密钥由本地后端环境变量管理，页面只读；请求统计保存在本机。真实采集可能产生服务商费用。" /> : null}

              <div className="business-config__categories" role="group" aria-label="服务分类">
                <strong>服务分类</strong>
                <div className="business-config__category-buttons">
                  {BUSINESS_CONFIG_CATEGORIES.map((item) => (
                    <Button key={item.key} size="small" type={category === item.key ? "primary" : "default"}
                      ghost={category === item.key} onClick={() => setCategory(item.key)}>
                      {item.label}<span className="business-config__count">{categoriesCount(item.key)}</span>
                    </Button>
                  ))}
                </div>
              </div>

              <Card className="business-config__list-card" title={category === "all" ? "全部服务" : BUSINESS_CONFIG_CATEGORIES.find((item) => item.key === category)?.label}
                extra={<Space><span className="business-config__muted">{filteredRows.length} 个实例</span>{canEdit && <Button size="small" icon={<PlusOutlined />} onClick={() => openServiceEditor()}>新增配置</Button>}</Space>}>
                <div className="business-config__filters">
                  <Input.Search aria-label="搜索服务配置" allowClear placeholder="搜索服务名称、实例、业务用途"
                    value={keyword} onChange={(event) => setKeyword(event.target.value)} className="business-config__search" />
                  <Select aria-label="状态筛选" value={statusFilter} onChange={setStatusFilter} className="business-config__status-filter"
                    options={[{ value: "all", label: "全部状态" }, { value: "已启用", label: "已启用" }, { value: "已停用", label: "已停用" }, { value: "未配置", label: "未配置" }]} />
                  <span className="business-config__filter-spacer" />
                  <Segmented value={viewMode} onChange={(value) => setViewMode(value as ViewMode)}
                    options={[{ label: <TableOutlined />, value: "table" }, { label: <AppstoreOutlined />, value: "cards" }]} />
                </div>

                {liveError && <Alert type="warning" showIcon message="飞书与 AI 连接暂时无法读取" description="已保留 Decodo 数据和现有设计草稿，请检查后端服务及测试库。"
                  action={<Button size="small" onClick={() => void refreshConnectors()}>重试</Button>} />}
                {viewMode === "table" ? (
                  <Table<ServiceRow> rowKey="key" size="small" loading={configLoading || liveLoading} dataSource={filteredRows} columns={columns}
                    locale={{ emptyText: <Empty description="该分类暂无服务配置" /> }} pagination={false} scroll={{ x: 970 }} />
                ) : (
                  <div className="business-config__cards">
                    {filteredRows.map((item) => <div key={item.key} className="business-config__instance">
                      <div className="business-config__instance-head">
                        <span className="business-config__service-avatar">{item.decodo ? "DE" : item.category === "ai" ? "AI" : "飞"}</span>
                        <div><strong>{item.name}</strong><span className="business-config__subline">{item.subtitle}</span></div>
                        <Tag color={item.state === "已启用" ? "success" : "default"}>{item.state}</Tag>
                      </div>
                      <p>{item.purpose}</p><div className="business-config__instance-meta"><span>{item.billing}</span><span>{item.updated}</span></div>
                      <Space><Button size="small" onClick={() => item.decodo ? setDetailsOpen(true) : openServiceEditor(item.connector, item.draft)}>详情</Button>
                        {canEdit && <Button size="small" onClick={() => item.decodo ? openEditor() : openServiceEditor(item.connector, item.draft)}>编辑</Button>}</Space>
                    </div>)}
                    {filteredRows.length === 0 && <Empty description="该分类暂无服务配置" />}
                  </div>
                )}
                <div className="business-config__list-footer">共 {filteredRows.length} 条配置 · 飞书和 AI 以实际后端状态为准，草稿未建立真实连接</div>
              </Card>
            </div>
          ) : section === "usage" ? (
            <div className="business-config__body">
              <Alert type="info" showIcon message="用量数据为真实接口统计，暂不包含供应商计费金额"
                description="当前 Decodo 按实际发起的请求尝试计数（含失败）；官方计费请求可能不同。暂不提供没有计价依据的美元估算。" />
              <div className="business-config__usage-toolbar">
                <Space>
                  <Segmented value={usageRange} onChange={(value) => { setUsageLoading(true); setUsageRange(value as UsageRange); }}
                    options={[{ label: "最近 7 天", value: 7 }, { label: "最近 30 天", value: 30 }]} />
                  <Tag>Decodo</Tag>
                </Space>
                <Button icon={<ReloadOutlined />} loading={usageLoading} onClick={() => void loadUsage(usageRange)}>刷新用量</Button>
              </div>
              {usageError ? <Alert type="error" showIcon message="用量读取失败，请检查后端及权限" /> : null}
              <div className="business-config__stats">
                <Card><Statistic title="今日请求" value={usageError ? "—" : todayRow?.total ?? 0} /><span>America/New_York</span></Card>
                <Card><Statistic title="Amazon 请求" value={usageError ? "—" : todayRow?.amazon_requests ?? 0} /><span>今日采集请求</span></Card>
                <Card><Statistic title="Walmart 请求" value={usageError ? "—" : todayRow?.walmart_requests ?? 0} /><span>今日采集请求</span></Card>
                <Card><Statistic title="所选区间请求" value={usageError ? "—" : totalRequests} /><span>包含成功、失败及处理中</span></Card>
              </div>
              <div className="business-config__usage-grid">
                <Card title="每日请求趋势" className="business-config__chart">
                  {usageLoading ? <span className="business-config__muted">正在加载统计数据…</span> : usageError ? <Empty description="用量数据不可用" /> : (
                    <div className="business-config__chart-scroll">
                      <div className="business-config__chart-bars" role="img" aria-label="Decodo 每日请求数柱状图">
                        {chartRows.map((row) => (
                          <div key={row.date} className="business-config__chart-column" title={row.date + "：" + row.total + " 次请求"}>
                            <span className="business-config__chart-value">{row.total}</span>
                            <div className="business-config__bar-track"><span style={{ height: (row.total ? Math.max(4, row.total / chartMax * 100) : 0) + "%" }} /></div>
                            <span className="business-config__chart-day">{row.date.slice(5)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </Card>
                <Card title="费用核算状态" className="business-config__billing-card">
                  <div className="business-config__billing-placeholder">—</div>
                  <strong>尚未配置计价规则</strong>
                  <p>当前接口只记录 Decodo 请求尝试。待接入实际套餐、单位价格及供应商账单后，才能显示每日美元成本。</p>
                  <Tag color="warning">计费未启用</Tag>
                </Card>
              </div>
              <Card className="business-config__related-panel"><LiveBusinessConnectors section="usage" canManage={canEdit} category="all" keyword="" status="all" /></Card>
              <Card title="Decodo 每日调用明细" className="business-config__detail">
                <Table<DecodoUsageDay> size="small" rowKey="date" loading={usageLoading} pagination={{ pageSize: 10, showSizeChanger: false }}
                  dataSource={usageError ? [] : usageRows} columns={[
                    { title: "美国日期", dataIndex: "date" },
                    { title: "Amazon", dataIndex: "amazon_requests" },
                    { title: "Walmart", dataIndex: "walmart_requests" },
                    { title: "总请求", dataIndex: "total" },
                    { title: "成功", dataIndex: "success" },
                    { title: "失败", dataIndex: "failed" },
                    { title: "处理中", dataIndex: "pending" },
                  ]} />
              </Card>
            </div>
          ) : (
            <div className="business-config__body">
              <Alert type="info" showIcon message="只显示当前 Decodo 后端已支持的配置策略"
                description="预算限制、故障切换、AI 默认模型及通知路由需要独立的后端支持；本页不会提供无法生效的模拟开关。" />
              <Card title="Decodo 当前策略" className="business-config__policy-card" loading={configLoading}>
                {configError ? <Alert showIcon type="error" message="配置状态读取失败" /> : config ? (
                  <div className="business-config__policy-grid">
                    <div><span>服务启用</span><Tag color={config.enabled ? "success" : "default"}>{config.enabled ? "启用" : "停用"}</Tag></div>
                    <div><span>采集地区 ZIP</span><strong>{config.us_zip}</strong></div>
                    <div><span>认证状态</span><Tag color={config.configured ? "success" : "warning"}>{config.configured ? "已配置" : "未配置"}</Tag></div>
                    <div><span>运行模式</span><strong>{isLocalMode ? "本地 SQLite 测试" : "数据库配置"}</strong></div>
                    <div><span>最近更新</span><strong>{labelDate(config.updated_at)}</strong></div>
                    <div><span>修改权限</span><strong>超级管理员</strong></div>
                    {canEdit && !isLocalMode ? <Button type="primary" onClick={openEditor}>编辑现有策略</Button> : null}
                  </div>
                ) : <Empty description="尚未读取到 Decodo 配置" />}
              </Card>
              <Card className="business-config__related-panel"><LiveBusinessConnectors section="policies" canManage={canEdit} category="all" keyword="" status="all" /></Card>
              <Card><BusinessConfigDraftManager section="policies" category="all" keyword="" status="all" canManage={canEdit}/></Card>
            </div>
          )}
        </div>
      </PageShell>

      <BusinessConfigServiceEditor open={editorOpen} connector={editingLive} draft={editingDraft}
        preferredCategory={category} onClose={() => setEditorOpen(false)} onSaved={() => void refreshConnectors()} />
      <Drawer title="Decodo · 配置详情" width={480} open={detailsOpen} onClose={() => setDetailsOpen(false)}>
        <Alert type="info" showIcon message="真实 Decodo 后端配置" description="与浏览器内的配置草稿分离；当前后端仅支持一个 Decodo 系统实例。" />
        <div className="business-config__form">
          <strong>认证状态</strong><span>{config?.configured ? "已配置" : "未配置"}</span>
          <strong>服务状态</strong><span>{config ? decodoStatus(config) : "未读取"}</span>
          <strong>美国 ZIP Code</strong><span>{config?.us_zip ?? "—"}</span>
          <strong>运行模式</strong><span>{isLocalMode ? "本地 SQLite 测试" : "数据库"}</span>
          <strong>最近更新</strong><span>{labelDate(config?.updated_at)}</span>
          <strong>今日请求次数</strong><span>{usageError ? "读取失败" : (todayRow?.total ?? 0)}</span>
          <strong>计费方式</strong><span>未配置计价</span>
          <strong>授权凭据</strong><span>不回显、不进入浏览器存储</span>
          {canEdit && !isLocalMode && <Button type="primary" onClick={() => { setDetailsOpen(false); openEditor(); }}>编辑真实 Decodo 配置</Button>}
          {isLocalMode && <Alert type="warning" showIcon message="本地测试模式使用后端环境变量，不能在此编辑真实授权。" />}
        </div>
      </Drawer>
      <Drawer className="business-config__drawer" title="Decodo · 编辑配置" width={520} open={drawerOpen}
        destroyOnHidden maskClosable={!saving} closable={!saving} onClose={() => setDrawerOpen(false)}
        extra={<Space><Button disabled={saving} onClick={() => setDrawerOpen(false)}>取消</Button>
          <Button type="primary" loading={saving} onClick={() => void save()}>保存配置</Button></Space>}>
        <Alert showIcon type="info" message="已有凭据不会回显" description="仅在需要轮换密钥时填写新的 Basic Authorization；留空表示沿用已保存的凭据。" />
        <div className="business-config__form">
          <label htmlFor="business-config-auth">Authorization (Basic)</label>
          <Input.Password id="business-config-auth" autoComplete="new-password" value={draftAuthorization}
            onChange={(event) => setDraftAuthorization(event.target.value)} placeholder="留空保持原密钥" />
          <label htmlFor="business-config-zip">美国 ZIP Code</label>
          <Input id="business-config-zip" maxLength={5} value={draftZip} onChange={(event) => setDraftZip(event.target.value.replace(/\D/g, ""))} />
          <div className="business-config__switch-line"><span>启用 Decodo</span><Switch checked={draftEnabled} onChange={setDraftEnabled} /></div>
          <div className="business-config__form-note">此保存操作会更新真实的 Decodo 服务配置；不运行采集、重试或历史同步。</div>
        </div>
      </Drawer>
    </>
  );
}
