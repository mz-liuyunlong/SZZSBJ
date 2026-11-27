import { forwardRef, useImperativeHandle, useState, type ReactNode } from "react";
import { InputNumber, Switch, Tabs, Tag, Tooltip } from "antd";
import { QuestionCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import "./trackingRuleConfigV2.css";

/** V1 configuration demo. Browser-local draft only; NOT a backend business-rule API. */
export type TrackingRuleConfigHandle = { save: () => boolean };

type TrackingRuleDraft = {
  successStartDay: number;
  focusStartDay: number;
  focusEndDay: number;
  availableCoveragePct: number;
  healthyMarginPct: number;
  recentLossDays: number;
  sustainedLossDays: number;
  marginDropPoints: number;
  profitDropPct: number;
  lowVolumeDailyOrders: number;
  lowVolumeProtection: boolean;
  profitDeteriorationAlert: boolean;
  stockAttentionDays: number;
  stockSevereDays: number;
  stockSafetyDays: number;
  replenishmentAttentionDays: number;
  replenishmentSevereDays: number;
  inventoryRiskAlert: boolean;
  notifyRecommendationChange: boolean;
  notifyMajorRisk: boolean;
  notifyMilestones: boolean;
};

const STORAGE_KEY = "szzsbj.new_product.tracking_rule_v1.local_draft";
const DEFAULTS: TrackingRuleDraft = {
  successStartDay: 15,
  focusStartDay: 15,
  focusEndDay: 45,
  availableCoveragePct: 80,
  healthyMarginPct: 8,
  recentLossDays: 14,
  sustainedLossDays: 30,
  marginDropPoints: 5,
  profitDropPct: 20,
  lowVolumeDailyOrders: 3,
  lowVolumeProtection: true,
  profitDeteriorationAlert: true,
  stockAttentionDays: 90,
  stockSevereDays: 180,
  stockSafetyDays: 15,
  replenishmentAttentionDays: 120,
  replenishmentSevereDays: 180,
  inventoryRiskAlert: true,
  notifyRecommendationChange: true,
  notifyMajorRisk: true,
  notifyMilestones: true,
};

type NumericKey = {
  [K in keyof TrackingRuleDraft]: TrackingRuleDraft[K] extends number ? K : never;
}[keyof TrackingRuleDraft];
type BooleanKey = {
  [K in keyof TrackingRuleDraft]: TrackingRuleDraft[K] extends boolean ? K : never;
}[keyof TrackingRuleDraft];

function loadLocalDraft(): TrackingRuleDraft {
  if (typeof window === "undefined") return { ...DEFAULTS };
  try {
    const text = window.localStorage.getItem(STORAGE_KEY);
    if (!text) return { ...DEFAULTS };
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return { ...DEFAULTS };
    const values = parsed as Record<string, unknown>;
    const result: Record<string, number | boolean> = { ...DEFAULTS };
    for (const key of Object.keys(DEFAULTS) as Array<keyof TrackingRuleDraft>) {
      const candidate = values[key];
      if (typeof candidate === typeof DEFAULTS[key] &&
          (typeof candidate !== "number" || Number.isFinite(candidate))) {
        result[key] = candidate as number | boolean;
      }
    }
    return result as unknown as TrackingRuleDraft;
  } catch {
    return { ...DEFAULTS };
  }
}

function validate(d: TrackingRuleDraft): string | null {
  const numbers: NumericKey[] = [
    "successStartDay", "focusStartDay", "focusEndDay", "availableCoveragePct",
    "healthyMarginPct", "recentLossDays", "sustainedLossDays", "marginDropPoints",
    "profitDropPct", "lowVolumeDailyOrders", "stockAttentionDays", "stockSevereDays",
    "stockSafetyDays", "replenishmentAttentionDays", "replenishmentSevereDays",
  ];
  if (numbers.some(k => !Number.isFinite(d[k]) || d[k] < 0)) return "所有数值必须是有效的非负数字";
  if (d.successStartDay < 1 || d.focusStartDay < 1 || d.focusEndDay < d.focusStartDay || d.successStartDay > d.focusEndDay) {
    return "成功建议起始日和重点观察区间不符合先后顺序";
  }
  if (d.availableCoveragePct <= 0 || d.availableCoveragePct > 100 || d.healthyMarginPct > 100 || d.profitDropPct > 100) {
    return "百分比必须在有效范围内";
  }
  if (d.recentLossDays < 1 || d.sustainedLossDays <= d.recentLossDays) return "持续亏损观察期必须长于近期亏损观察期";
  if (d.marginDropPoints <= 0 || d.profitDropPct <= 0 || d.lowVolumeDailyOrders <= 0) return "利润恶化和低销量保护阈值必须大于0";
  if (d.stockAttentionDays < 1 || d.stockSevereDays <= d.stockAttentionDays) return "长期库存风险线必须高于库存关注线";
  if (d.replenishmentAttentionDays < 1 || d.replenishmentSevereDays <= d.replenishmentAttentionDays) return "补货严重风险线必须高于补货关注线";
  return null;
}

function Help({ example }: { example: string }) {
  return (
    <Tooltip placement="top" title={<span className="np-trv2-example">{example}</span>}>
      <QuestionCircleOutlined className="np-trv2-help" aria-label="鼠标移入查看规则示例" />
    </Tooltip>
  );
}

function Field({ label, example, children }: { label: string; example: string; children: ReactNode }) {
  return (
    <div className="np-trv2-field">
      <div className="np-trv2-field-title"><span>{label}</span><Help example={example} /></div>
      <div className="np-trv2-field-control">{children}</div>
    </div>
  );
}

const TrackingRuleConfigPanel = forwardRef<TrackingRuleConfigHandle>(function TrackingRuleConfigPanel(_, ref) {
  const [draft, setDraft] = useState<TrackingRuleDraft>(loadLocalDraft);
  const [activeTab, setActiveTab] = useState("observation");
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changeNumber = (key: NumericKey, value: number | null) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return;
    setDraft(old => ({ ...old, [key]: value }));
    setDirty(true);
    setError(null);
  };
  const changeBool = (key: BooleanKey, value: boolean) => {
    setDraft(old => ({ ...old, [key]: value }));
    setDirty(true);
    setError(null);
  };
  const num = (key: NumericKey, unit: string, min = 0, max = 10000) => (
    <div className="np-trv2-input-wrap">
      <InputNumber<number>
        className="np-trv2-input"
        controls={false}
        size="middle"
        min={min}
        max={max}
        precision={0}
        value={draft[key]}
        onChange={v => changeNumber(key, v)}
      />
      <span className="np-trv2-unit">{unit}</span>
    </div>
  );
  const toggle = (key: BooleanKey) => <Switch size="small" checked={draft[key]} onChange={v => changeBool(key, v)} />;

  const saveDraft = (): boolean => {
    const issue = validate(draft);
    if (issue) {
      setError(issue);
      return false;
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
      setDirty(false);
      setError(null);
      return true;
    } catch {
      setError("无法写入浏览器本地草稿；请检查隐私模式或本地存储权限");
      return false;
    }
  };
  useImperativeHandle(ref, () => ({ save: saveDraft }), [draft]);

  const tabs = [
    {
      key: "observation",
      label: "观察与建议",
      children: (
        <div className="np-trv2-tab-content">
          <div className="np-trv2-section-heading">观察周期与判定窗口 <span>自然日观察；有效可售天数校验</span></div>
          <div className="np-trv2-grid">
            <Field label="成功建议最早开售日" example="第15天起可以根据真实盈利和资金风险提出早期成功建议；第12天即使盈利，也仅显示积极信号。">{num("successStartDay", "天", 1, 365)}</Field>
            <Field label="重点人工判定开始" example="运营通常在第15至45天做人工判定。这里是重点提示窗口，不阻止运营更早判定。">{num("focusStartDay", "天", 1, 365)}</Field>
            <Field label="重点人工判定结束" example="第45天不是强制截止日；未判定商品仍持续每日分析。">{num("focusEndDay", "天", 1, 365)}</Field>
            <Field label="有效可售数据覆盖率" example="开售30天中，只有20天数据可靠，覆盖率66.7%，低于80%时提示样本不足。">{num("availableCoveragePct", "%", 1, 100)}</Field>
          </div>
          <div className="np-trv2-info"><strong>固定规则</strong><span>首次 Listing 实际可售且有可履约库存起算；观察节点30 / 60 / 180天；每天自动分析，人工结果不被自动覆盖。</span><Help example="例如11月1日首次有可履约库存且Listing可售，从这一天开始累计自然日。中间缺货不重置开售日期，但降低有效可售覆盖率。" /></div>
          <div className="np-trv2-priority"><b>系统主建议优先级</b><span>数据可信 → 严格失败复核 → 重大经营风险 → 盈利考虑成功 → 普通优化 → 继续观察</span><Help example="第25天累计贡献利润为正、资金可控时，可建议早期成功；广告普通优化问题独立附加。持续亏损加重大资金风险、没有改善时，才建议复核失败。" /></div>
        </div>
      ),
    },
    {
      key: "profit",
      label: "利润风险",
      children: (
        <div className="np-trv2-tab-content">
          <div className="np-trv2-section-heading">利润观察参数 <span>B1贡献利润口径固定，不按销量设置成功门槛</span></div>
          <div className="np-trv2-grid">
            <Field label="健康利润率参考" example="销售净收入1,000美元、贡献利润90美元，利润率9%，高于8%健康参考线。5%仍然是盈利，不因此判失败。">{num("healthyMarginPct", "%", 0, 100)}</Field>
            <Field label="近期亏损观察期" example="最近14天贡献利润为负，提示近期亏损，但不会单凭这一项建议打品失败。">{num("recentLossDays", "天", 1, 180)}</Field>
            <Field label="持续亏损观察期" example="最近30天亏损、最近14天仍亏损，识别持续亏损风险；失败复核还要满足额外负面证据。">{num("sustainedLossDays", "天", 2, 365)}</Field>
            <Field label="利润率恶化幅度" example="上个14天利润率15%，本期9%，下降6个百分点，超过5个百分点门槛。">{num("marginDropPoints", "百分点", 1, 100)}</Field>
            <Field label="利润金额恶化幅度" example="上期利润100美元，本期75美元，下降25%。与利润率恶化门槛同时满足才触发提醒。">{num("profitDropPct", "%", 1, 100)}</Field>
            <Field label="低销量保护参考" example="日均1单的商品按较长30/60天窗口看趋势，不因单量低否定它的正向贡献利润。">{num("lowVolumeDailyOrders", "单/天", 1, 100)}</Field>
            <Field label="低销量稳健分析" example="开启后，日均低于3单的商品优先使用完整30/60天窗口；仍然及时显示真实亏损和资金损失。">{toggle("lowVolumeProtection")}</Field>
            <Field label="利润恶化提醒" example="利润率降幅达到门槛且同期利润金额降幅同时达到门槛，提示利润恶化，不自动判失败。">{toggle("profitDeteriorationAlert")}</Field>
          </div>
          <div className="np-trv2-info"><strong>计算口径不可关闭</strong><span>收入减已售采购、头程、佣金、履约、广告、退款等可归属经营费用；成本缺失不能按0计算。</span><Help example="采购了300件，但只卖出20件，计算本期经营利润只确认已售20件对应成本，其余仍是库存资金占用。" /></div>
        </div>
      ),
    },
    {
      key: "capital",
      label: "库存与补货",
      children: (
        <div className="np-trv2-tab-content">
          <div className="np-trv2-section-heading">库存资金风险 <span>参考线结合真实补货周期动态修正</span></div>
          <div className="np-trv2-grid">
            <Field label="库存覆盖关注" example="补货周期45天、安全库存15天：max(90,45+15+30)=90天，覆盖超出后提醒关注。">{num("stockAttentionDays", "天", 1, 1000)}</Field>
            <Field label="长期库存风险" example="补货周期120天、安全库存15天：max(180,120+15+90)=225天，不会误伤正常长周期备货。">{num("stockSevereDays", "天", 1, 2000)}</Field>
            <Field label="安全库存缓冲" example="日均1单，补货周期45天，安全库存15天，基础补货检查点约为60件。">{num("stockSafetyDays", "天", 0, 365)}</Field>
            <Field label="补货后覆盖关注" example="预计新货到达时还有20件，拟补100件，日均1单，则补货后预计可卖120天。">{num("replenishmentAttentionDays", "天", 1, 2000)}</Field>
            <Field label="补货后严重参考" example="补货后可卖300天不直接等于重大风险；还要有实际滞留资金或现金压力证据。">{num("replenishmentSevereDays", "天", 1, 3000)}</Field>
            <Field label="库存资金风险提醒" example="开启后，库存积压或补货过量时会展示风险依据；未超过重大门槛时不推翻盈利商品的成功建议。">{toggle("inventoryRiskAlert")}</Field>
          </div>
          <div className="np-trv2-info"><strong>固定双重证据</strong><span>重大风险 = 动态严重阈值超标 + 可信的资金压力/滞留金额/追加投入问题；不能单凭库存180天判严重。</span><Help example="商品每月赚150美元，但库存价值6,000美元、预计覆盖300天，需同时核查资金滞留金额与补货需求；先建议优化，不直接判失败。" /></div>
        </div>
      ),
    },
    {
      key: "notifications",
      label: "提醒与范围",
      children: (
        <div className="np-trv2-tab-content">
          <div className="np-trv2-section-heading">运营自动提醒 <span>每天计算，但不每天发送重复通知</span></div>
          <div className="np-trv2-grid">
            <Field label="主建议变化提醒" example="昨天建议继续观察，今天变成建议优化经营，提醒负责人一次。">{toggle("notifyRecommendationChange")}</Field>
            <Field label="重大风险变化提醒" example="首次出现重大库存风险、风险升级或解除时提醒；同一未变化风险不重复提醒。">{toggle("notifyMajorRisk")}</Field>
            <Field label="观察节点提醒" example="首次达到30/60/180个自然观察日时提醒，不代表必须人工判定。">{toggle("notifyMilestones")}</Field>
            <Field label="重复提醒控制" example="同一建议及同一风险在未变化期间，不应每天重复创建待办；该行为始终固定启用。"><Tag color="default">固定：不重复提醒</Tag></Field>
          </div>
          <div className="np-trv2-info"><strong>全店统一 / 人工决定</strong><span>原始经营事实、数据可信校验、系统建议历史与人工最终判定不可关闭。</span><Help example="系统建议成功，运营仍可选择继续观察或失败，但需根据既定要求填写相关理由；系统不能代替点击或改写人工结论。" /></div>
          <div className="np-trv2-exclusions"><b>V1 不应用：</b><Tag>真实资金回收与回本天数</Tag><Tag>维护人效</Tag><Tag>历史商品自动补算</Tag></div>
          <div className="np-trv2-note">规则全店统一。仅作为浏览器本地可编辑草稿；正式分析引擎、权限控制和数据库保存仍需后端接口支持。</div>
        </div>
      ),
    },
  ];

  return (
    <div className="np-trv2-root">
      <div className="np-trv2-head">
        <div>
          <div className="np-trv2-title">全店统一 · 打品辅助规则 <Tag color="blue">V1</Tag></div>
          <div className="np-trv2-subtitle">每日自动分析 · 第15天起提供成功建议 · 最终人工判定</div>
        </div>
        <div className="np-trv2-head-right">
          <Tag color={dirty ? "orange" : "default"}>{dirty ? "有未保存修改" : "浏览器本地草稿"}</Tag>
          <button className="np-trv2-reset" type="button" onClick={() => { setDraft({ ...DEFAULTS }); setDirty(true); setError(null); }}><ReloadOutlined /> 恢复默认</button>
          <button className="np-trv2-save" type="button" onClick={saveDraft}>保存草稿</button>
        </div>
      </div>
      <Tabs className="np-trv2-tabs" size="small" activeKey={activeTab} onChange={setActiveTab} items={tabs} animated={false} />
      {error && <div className="np-trv2-error" role="alert">{error}</div>}
      <div className="np-trv2-bottom-note">鼠标移入字段后的 <QuestionCircleOutlined /> 查看计算示例。修改后点击右上角「保存草稿」，仅保存于当前浏览器。</div>
    </div>
  );
});

export default TrackingRuleConfigPanel;
