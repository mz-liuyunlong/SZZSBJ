import {
  ApiOutlined,
  AppstoreOutlined,
  BarChartOutlined,
  CloudOutlined,
  EditOutlined,
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

  const matchesCategory = category === "all" || category === "crawler";
  const matchesKeyword = "decodo scraper api 爬虫与代理 商品信息采集 amazon walmart"
    .includes(keyword.toLowerCase().trim());
  const matchesStatus = statusFilter === "all"
    || (config != null && decodoStatus(config) === statusFilter);
  const visible = Boolean(config && matchesCategory && matchesKeyword && matchesStatus);

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

  const columns: ColumnsType<DecodoConfig> = [
    {
      title: "服务 / 配置名称",
      key: "name",
      width: 250,
      render: () => (
        <Space>
          <span className="business-config__service-avatar">DE</span>
          <span>
            <strong>Decodo Scraper API</strong>
            <span className="business-config__subline">Decodo · 爬虫与代理</span>
          </span>
        </Space>
      ),
    },
    { title: "配置实例", key: "instance", width: 130, render: () => "系统默认实例" },
    { title: "业务用途", key: "purpose", render: () => "Amazon / Walmart 商品信息采集" },
    {
      title: "状态",
      key: "status",
      width: 115,
      render: (_, record) => {
        const status = decodoStatus(record);
        return <Tag color={status === "已启用" ? "success" : status === "未配置" ? "warning" : "default"}>{status}</Tag>;
      },
    },
    {
      title: "今日请求",
      key: "calls",
      width: 110,
      render: () => usageError ? "读取失败" : (usageLoading ? "加载中" : (todayRow?.total ?? 0)),
    },
    {
      title: "计费",
      key: "billing",
      width: 130,
      render: () => <span className="business-config__muted">未配置计价</span>,
    },
    { title: "最近修改", dataIndex: "updated_at", width: 160, render: labelDate },
    {
      title: "操作",
      key: "actions",
      width: 170,
      fixed: "right",
      render: () => (
        <Space size={0}>
          <Button type="link" size="small" onClick={goToUsage}>用量</Button>
          {canEdit && !isLocalMode ? <Button type="link" size="small" onClick={openEditor}>编辑</Button> : null}
        </Space>
      ),
    },
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
            <Button icon={<ReloadOutlined />} loading={configLoading || usageLoading}
              onClick={() => { void loadConfig(); void loadUsage(usageRange); }}>刷新数据</Button>
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
                <Card><Statistic title="已接入服务" value={config ? 1 : 0} prefix={<LinkOutlined />} /><span>实际接入的服务实例</span></Card>
                <Card><Statistic title="已启用连接" value={config?.enabled ? 1 : 0} prefix={<SafetyCertificateOutlined />} /><span>由后端配置状态决定</span></Card>
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
                      {item.label}<span className="business-config__count">{item.key === "all" || item.key === "crawler" ? (config ? 1 : 0) : 0}</span>
                    </Button>
                  ))}
                </div>
              </div>

              <Card className="business-config__list-card" title={category === "all" ? "全部服务" : BUSINESS_CONFIG_CATEGORIES.find((item) => item.key === category)?.label}
                extra={<span className="business-config__muted">{visible ? "1 个实例" : "0 个实例"}</span>}>
                <div className="business-config__filters">
                  <Input.Search aria-label="搜索服务配置" allowClear placeholder="搜索服务名称、实例、业务用途"
                    value={keyword} onChange={(event) => setKeyword(event.target.value)} className="business-config__search" />
                  <Select aria-label="状态筛选" value={statusFilter} onChange={setStatusFilter} className="business-config__status-filter"
                    options={[{ value: "all", label: "全部状态" }, { value: "已启用", label: "已启用" }, { value: "已停用", label: "已停用" }, { value: "未配置", label: "未配置" }]} />
                  <span className="business-config__filter-spacer" />
                  <Segmented value={viewMode} onChange={(value) => setViewMode(value as ViewMode)}
                    options={[{ label: <TableOutlined />, value: "table" }, { label: <AppstoreOutlined />, value: "cards" }]} />
                </div>

                {viewMode === "table" ? (
                  <Table<DecodoConfig> rowKey={() => "decodo"} size="small" loading={configLoading}
                    dataSource={visible && config ? [config] : []} columns={columns}
                    locale={{ emptyText: <Empty description={category === "all" || category === "crawler" ? "暂无匹配的服务配置" : "该分类尚无接入的服务"} /> }}
                    pagination={false} scroll={{ x: 1150 }} />
                ) : (
                  <div className="business-config__cards">
                    {visible && config ? (
                      <div className="business-config__instance">
                        <div className="business-config__instance-head">
                          <span className="business-config__service-avatar">DE</span>
                          <div><strong>Decodo Scraper API</strong><span className="business-config__subline">爬虫与代理 · 系统默认实例</span></div>
                          <Tag color={config.enabled ? "success" : config.configured ? "default" : "warning"}>{decodoStatus(config)}</Tag>
                        </div>
                        <p>Amazon / Walmart 商品信息采集</p>
                        <div className="business-config__instance-meta">
                          <span>今日请求：{usageError ? "读取失败" : (todayRow?.total ?? 0)}</span>
                          <span>费用：未配置计价</span>
                          <span>更新：{labelDate(config.updated_at)}</span>
                        </div>
                        <Space>
                          <Button size="small" onClick={goToUsage}>查看用量</Button>
                          {canEdit && !isLocalMode ? <Button size="small" type="primary" icon={<EditOutlined />} onClick={openEditor}>编辑配置</Button> : null}
                        </Space>
                      </div>
                    ) : <Empty description="该分类暂无匹配的已接入服务" />}
                  </div>
                )}
                <div className="business-config__list-footer">当前只接入 Decodo 单实例。其他服务将在后端接入后展示，不使用演示账号或虚构费用。</div>
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
            </div>
          )}
        </div>
      </PageShell>

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
