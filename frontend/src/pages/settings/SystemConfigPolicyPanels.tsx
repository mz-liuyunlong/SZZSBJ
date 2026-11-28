import { Button, Card, Col, Empty, Input, InputNumber, Menu, Row, Select, Space, Tag, Typography } from "antd";
import { useState } from "react";

type Field = { key: string; label: string; hint: string; unit?: string; min?: number; max?: number; options?: string[]; readOnly?: boolean };
type Group = { key: string; title: string; description: string; fields: Field[] };
type Value = string | number;
type Values = Record<string, Value | undefined>;
const numericField = (key: string, label: string, unit: string, hint: string, min = 1, max = 1000000): Field => ({ key, label, unit, hint, min, max });
const choice = (key: string, label: string, options: string[], hint: string): Field => ({ key, label, options, hint });
const text = (key: string, label: string, hint: string, readOnly = false): Field => ({ key, label, hint, readOnly });
const policyGroups: Group[] = [
  { key: "request", title: "请求控制", description: "限制单次请求的连接与响应时间，以及调用频率。", fields: [numericField("connect", "连接超时", "秒", "建立网络连接的最长等待时间", 1, 120), numericField("timeout", "请求超时", "秒", "单次请求的最长等待时间", 1, 600), numericField("rps", "每秒请求上限", "次", "不超过平台实际限额"), numericField("rpm", "每分钟请求上限", "次", "与每秒限额同时生效")] },
  { key: "batch", title: "批量控制", description: "按接口能力控制批次与分页，避免超大响应。", fields: [numericField("batch", "单批处理数量", "条", "批量写入需满足平台上限"), numericField("page", "分页大小", "条", "单次读取数量"), numericField("pages", "最大分页数", "页", "限制单次任务遍历范围"), numericField("body", "响应体大小上限", "MB", "限制单次响应大小")] },
  { key: "retry", title: "失败重试", description: "仅对可安全重试的错误应用策略，写入需保证幂等。", fields: [numericField("count", "最大重试次数", "次", "0 表示不重试", 0, 20), numericField("interval", "初始重试间隔", "秒", "遵守服务商 Retry-After", 1, 600), choice("backoff", "退避方式", ["固定间隔", "指数退避"], "控制连续重试间隔"), choice("errors", "重试范围", ["临时网络错误与限流", "仅临时网络错误"], "业务校验、权限错误不重试")] },
  { key: "resource", title: "资源调度", description: "多店铺和多账号共享接口资源，避免单一任务独占。", fields: [numericField("global", "全局并发上限", "个", "所有调用的总上限"), numericField("provider", "平台并发上限", "个", "每个平台的总上限"), numericField("account", "账号并发上限", "个", "同一授权账号共享限制"), numericField("store", "店铺并发上限", "个", "单店请求的同时执行数量")] },
  { key: "protection", title: "异常保护", description: "控制故障恢复与任务运行时长，不替代任务中心。", fields: [numericField("failures", "连续失败阈值", "次", "达到阈值后暂停自动调用"), numericField("cooldown", "熔断恢复时间", "秒", "冷却结束后受控探测"), numericField("duration", "任务最长执行时间", "分钟", "超时后的处理需按任务定义"), numericField("queue", "任务积压上限", "个", "限制等待执行的任务数量")] },
  { key: "data", title: "数据保护", description: "关键安全约束属于后端强制规则，不提供关闭按钮。", fields: [text("idempotency", "幂等与重复写入保护", "写入接口需要稳定业务标识及结果核对", true), text("empty", "空响应与异常数据校验", "不允许异常响应覆盖有效数据", true), text("overwrite", "数据覆盖保护", "必须校验数据完整性及更新范围", true)] },
  { key: "cache", title: "缓存策略", description: "只对适合缓存的读取接口配置，不缓存密钥。", fields: [numericField("ttl", "缓存有效期", "秒", "过期后重新获取数据"), numericField("retention", "缓存最长保留", "小时", "不得替代权威业务数据")] },
  { key: "monitor", title: "接口监控", description: "设置监测阈值，实际执行日志仍由日志模块管理。", fields: [numericField("slow", "慢请求阈值", "毫秒", "超过阈值标记慢请求"), numericField("failureRate", "失败率告警阈值", "%", "按统计窗口计算", 1, 100), numericField("window", "统计窗口", "分钟", "失败率统计范围")] },
  { key: "history", title: "变更历史", description: "后续读取真实配置审计记录。", fields: [] },
];
const parameterGroups: Group[] = [
  { key: "base", title: "基础参数", description: "只影响明确授权的展示范围，不改变报表及财务口径。", fields: [text("name", "系统名称", "系统品牌显示名称"), choice("lang", "默认显示语言", ["简体中文", "English"], "需对应实际语言资源"), choice("tz", "默认显示时区", ["Asia/Shanghai", "America/Los_Angeles", "America/New_York", "UTC"], "仅用于通用展示"), choice("currency", "默认显示币种", ["CNY", "USD"], "不改变财务核算币种")] },
  { key: "security", title: "登录安全", description: "会话及账号保护策略，正式接入时需验证安全边界。", fields: [numericField("session", "登录有效期", "小时", "会话最大有效时间", 1, 168), numericField("failed", "连续登录失败次数", "次", "触发账号保护的阈值", 1, 30), numericField("lock", "账号锁定时间", "分钟", "临时锁定时长", 1, 1440), numericField("password", "密码最小长度", "位", "不得低于安全基线", 12, 128), numericField("sessions", "同时登录会话上限", "个", "限制每个账号的有效会话数", 1, 100)] },
  { key: "files", title: "文件管理", description: "统一文件上传与临时文件管理。", fields: [numericField("upload", "单次上传大小上限", "MB", "还需符合服务端请求限制"), text("types", "允许文件类型", "例如 xlsx、csv；后续按上传业务校验"), numericField("temp", "临时文件保留周期", "天", "正式清理需明确存储范围")] },
  { key: "images", title: "图片管理", description: "控制素材处理和缓存，不影响原始产品图片。", fields: [numericField("size", "单张图片大小上限", "MB", "上传图片大小限制"), numericField("quality", "压缩质量", "%", "仅用于派生图片", 1, 100), numericField("thumbnail", "缩略图最大边长", "px", "派生图尺寸"), numericField("cache", "图片缓存周期", "天", "派生文件保留周期")] },
  { key: "export", title: "数据导出", description: "控制导出资源消耗和文件生命周期。", fields: [numericField("limit", "单次导出上限", "条", "不得突破数据权限范围"), numericField("async", "异步导出阈值", "条", "超过阈值使用后台任务"), numericField("expiry", "导出文件有效期", "天", "过期后的清理需单独接入")] },
  { key: "retention", title: "数据保留", description: "涉及审计及历史数据，预览不触发删除。", fields: [numericField("operation", "操作日志保留周期", "天", "需满足审计要求"), numericField("api", "接口日志保留周期", "天", "仅针对已确认可清理日志"), numericField("task", "任务记录保留周期", "天", "保留必要任务追溯证据"), text("raw", "原始数据保留规则", "按来源及业务审计要求独立制定", true)] },
  { key: "quality", title: "数据质量", description: "数据新鲜度与完整性按来源定义。", fields: [numericField("stale", "数据过期提示阈值", "小时", "不改变同步调度周期"), text("complete", "数据完整性检查", "按业务数据源的校验契约执行", true)] },
  { key: "performance", title: "系统性能", description: "统一列表与查询资源的基础限制。", fields: [choice("page", "默认分页数量", ["20", "50", "100"], "只用于采用该默认值的页面"), numericField("maxPage", "最大分页数量", "条", "不得超过接口安全限制"), numericField("query", "查询超时限制", "秒", "需按查询类型验证", 1, 600)] },
  { key: "maintenance", title: "系统维护", description: "维护操作属于高风险功能，当前不提供实际开关。", fields: [text("mode", "维护模式", "需独立权限、恢复机制与明确授权", true), text("notice", "维护公告", "维护期间显示给用户的说明")] },
  { key: "storage", title: "存储管理", description: "容量数据必须来自真实服务监控。", fields: [text("used", "已使用容量", "待接入监控", true), text("free", "剩余容量", "待接入监控", true), numericField("alert", "容量告警阈值", "%", "达到阈值触发告警", 1, 100)] },
  { key: "backup", title: "备份管理", description: "备份运行与恢复不通过本预览执行。", fields: [text("last", "最近备份时间", "待接入真实备份记录", true), text("status", "最近备份状态", "待接入真实备份记录", true), text("policy", "备份周期与保留策略", "由备份运行规范管理", true)] },
  { key: "history", title: "配置历史", description: "后续复用真实配置审计与版本记录。", fields: [] },
];
const providers = ["WooCommerce", "领星 ERP", "物流集成"];
const interfaces = ["商品查询", "商品刊登", "库存接口", "订单接口", "物流接口"];

function PolicyPanel({ policy }: { policy: boolean }) {
  const groups = policy ? policyGroups : parameterGroups;
  const [active, setActive] = useState(groups[0].key);
  const [scope, setScope] = useState("全局策略");
  const [provider, setProvider] = useState(providers[0]);
  const [endpoint, setEndpoint] = useState(interfaces[0]);
  const [previews, setPreviews] = useState<Record<string, Values>>({});
  const [draft, setDraft] = useState<Values | null>(null);
  const group = groups.find((item) => item.key === active) ?? groups[0];
  const prefix = policy ? JSON.stringify([scope, scope === "全局策略" ? "" : provider, scope === "接口级策略" ? endpoint : "", group.key]) : group.key;
  const current = previews[prefix] ?? {};
  const editable = group.fields.some((field) => !field.readOnly);
  const editing = draft !== null;
  const values = draft ?? current;
  const setValue = (key: string, value: Value | undefined) => setDraft((old) => {
    if (!old) return old;
    const next = { ...old };
    if (value === undefined || value === "") delete next[key];
    else next[key] = value;
    return next;
  });
  const valid = group.fields.every((field) => {
    const value = values[field.key];
    return value === undefined || !field.unit || (typeof value === "number" && Number.isInteger(value) && value >= (field.min ?? 0) && value <= (field.max ?? Infinity));
  });
  return (
    <Card title={policy ? "接口策略" : "系统参数"} extra={<Tag>设计预览 · 未接入</Tag>}>
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Typography.Text type="secondary">仅用于本地界面验收。参数不代表当前系统配置；预览修改不会保存或生效。</Typography.Text>
        {policy && <Space wrap>
          <Select aria-label="策略范围" value={scope} disabled={editing} style={{ width: 150 }} options={["全局策略", "平台策略", "接口级策略"].map((value) => ({ value, label: value }))} onChange={setScope} />
          {scope !== "全局策略" && <Select aria-label="平台" value={provider} disabled={editing} style={{ width: 150 }} options={providers.map((value) => ({ value, label: value }))} onChange={setProvider} />}
          {scope === "接口级策略" && <Select aria-label="接口类别" value={endpoint} disabled={editing} style={{ width: 150 }} options={interfaces.map((value) => ({ value, label: value }))} onChange={setEndpoint} />}
          <Typography.Text type="secondary">下级策略不得突破上级安全上限；接口类别为设计示例。</Typography.Text>
        </Space>}
        <Row gutter={[24, 16]} align="top">
          <Col xs={24} md={6} xl={4}>
            <Menu mode="inline" selectedKeys={[active]} items={groups.map((item) => ({ key: item.key, label: item.title, disabled: editing }))} onClick={({ key }) => setActive(key)} />
          </Col>
          <Col xs={24} md={18} xl={20}>
            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <Row justify="space-between" align="middle" gutter={[12, 8]}>
                <Col><Typography.Title level={5} style={{ margin: 0 }}>{group.title}</Typography.Title></Col>
                <Col>{editable && !editing && <Button onClick={() => setDraft({ ...current })}>编辑预览</Button>}</Col>
              </Row>
              <Typography.Text type="secondary">{group.description}</Typography.Text>
              {group.fields.length === 0 ? <Empty description="尚未接入真实历史记录" /> : <Row gutter={[24, 20]}>
                {group.fields.map((field) => <Col xs={24} lg={12} key={field.key}>
                  <Space direction="vertical" size={4} style={{ width: "100%" }}>
                    <Typography.Text strong>{field.label}</Typography.Text>
                    {field.readOnly ? <Typography.Text type="secondary">待接入 · 只读</Typography.Text> : field.unit ?
                      <Space.Compact block><InputNumber aria-label={field.label} value={typeof values[field.key] === "number" ? values[field.key] as number : null} min={field.min} max={field.max} precision={0} disabled={!editing} placeholder="未接入" style={{ width: "100%" }} onChange={(value) => setValue(field.key, value ?? undefined)} /><Button disabled>{field.unit}</Button></Space.Compact> : field.options ?
                        <Select aria-label={field.label} value={values[field.key] as string | undefined} placeholder="未接入" allowClear disabled={!editing} style={{ width: "100%" }} options={field.options.map((value) => ({ value, label: value }))} onChange={(value) => setValue(field.key, value)} /> :
                        <Input aria-label={field.label} value={values[field.key] ?? ""} disabled={!editing} placeholder="未接入" maxLength={200} onChange={(event) => setValue(field.key, event.target.value)} />}
                    <Typography.Text type="secondary">{field.hint}</Typography.Text>
                  </Space>
                </Col>)}
              </Row>}
              {editing && <Row justify="end"><Space><Button onClick={() => setDraft(null)}>取消</Button><Button type="primary" disabled={!valid} onClick={() => { setPreviews((old) => ({ ...old, [prefix]: draft ?? {} })); setDraft(null); }}>确认预览</Button></Space></Row>}
              {!editing && Object.keys(current).length > 0 && <Row justify="end"><Button type="link" onClick={() => setPreviews((old) => ({ ...old, [prefix]: {} }))}>清除预览</Button></Row>}
            </Space>
          </Col>
        </Row>
      </Space>
    </Card>
  );
}
export function ApiPolicyPanel() { return <PolicyPanel policy />; }
export function SystemParametersPanel() { return <PolicyPanel policy={false} />; }
