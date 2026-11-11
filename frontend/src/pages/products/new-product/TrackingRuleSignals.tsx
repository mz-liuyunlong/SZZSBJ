import { Popover, Tag } from "antd";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  WarningOutlined,
  InboxOutlined,
} from "@ant-design/icons";
import type { Product } from "./nativeData";
import "./trackingRuleSignals.css";

/** PR337_RULE_SIGNAL_POPOVER_V2
 * Only display rule conclusions that were supplied by an analysis snapshot.
 * Missing analysis != no triggered rules; no finance/stock results are guessed.
 */
type RuleTone = "positive" | "warning" | "danger" | "neutral";
type Recommendation = "success" | "observe" | "optimize" | "review_fail" | "insufficient";
type Signal = {
  code: string;
  title: string;
  explanation: string;
  tone: RuleTone;
};
type Presentation = {
  ready: boolean;
  recommendation: Recommendation;
  signals: Signal[];
  asOf?: string;
  period?: string;
  ruleVersion?: string;
};

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | undefined =>
  typeof v === "string" && v.trim() ? v.trim() : undefined;

const adviceText: Record<Recommendation, string> = {
  success: "建议打品成功",
  observe: "建议继续观察",
  optimize: "建议优化经营",
  review_fail: "建议复核失败",
  insufficient: "待分析",
};
const adviceTone: Record<Recommendation, string> = {
  success: "success",
  observe: "observe",
  optimize: "optimize",
  review_fail: "danger",
  insufficient: "insufficient",
};

function normalizeAdvice(raw: unknown): Recommendation {
  const label = str(raw)?.toLowerCase();
  if (["success", "consider_success", "建议考虑打品成功", "建议打品成功", "打品成功"].includes(label ?? "")) return "success";
  if (["observe", "continue_observe", "建议继续观察", "继续观察"].includes(label ?? "")) return "observe";
  if (["optimize", "optimize_operation", "建议优化经营", "需要优化"].includes(label ?? "")) return "optimize";
  if (["review_fail", "review_failure", "建议复核打品失败", "建议复核失败"].includes(label ?? "")) return "review_fail";
  return "insufficient";
}
function normalizeTone(raw: unknown): RuleTone {
  const label = str(raw)?.toLowerCase();
  if (["danger", "high", "severe", "critical"].includes(label ?? "")) return "danger";
  if (["warning", "medium", "attention"].includes(label ?? "")) return "warning";
  if (["positive", "success", "good"].includes(label ?? "")) return "positive";
  return "neutral";
}
function presentationFor(product: Product): Presentation {
  const fields = product as unknown as Record<string, unknown>;
  const candidate = fields.trackingRuleAnalysis ?? fields.tracking_rule_analysis;
  if (!isObject(candidate)) {
    return { ready: false, recommendation: "insufficient", signals: [] };
  }
  // A snapshot with no rules is valid only when its analyzer explicitly sent an empty array.
  const rawRules = candidate.triggeredRules ?? candidate.triggered_rules;
  if (!Array.isArray(rawRules)) {
    return { ready: false, recommendation: "insufficient", signals: [] };
  }
  const signals: Signal[] = rawRules.flatMap((item, index): Signal[] => {
    if (!isObject(item)) return [];
    const title = str(item.title ?? item.name ?? item.ruleName ?? item.rule_name);
    const explanation = str(item.explanation ?? item.reason ?? item.description ?? item.detail);
    if (!title) return [];
    return [{
      code: str(item.code ?? item.ruleId ?? item.rule_id) ?? `rule-${index}`,
      title,
      explanation: explanation ?? "当前规则已触发，详细计算依据待补充。",
      tone: normalizeTone(item.severity ?? item.level),
    }];
  });
  return {
    ready: true,
    recommendation: normalizeAdvice(candidate.recommendation ?? candidate.systemRecommendation ?? candidate.system_recommendation),
    signals,
    asOf: str(candidate.dataAsOf ?? candidate.data_as_of),
    period: str(candidate.period ?? candidate.observationWindow ?? candidate.observation_window),
    ruleVersion: str(candidate.ruleVersion ?? candidate.rule_version),
  };
}
function signalIcon(signal: Signal) {
  if (signal.code.toLowerCase().includes("stock") || signal.title.includes("库存")) return <InboxOutlined />;
  if (signal.tone === "danger" || signal.tone === "warning") return <WarningOutlined />;
  if (signal.tone === "positive") return <CheckCircleOutlined />;
  return <ClockCircleOutlined />;
}
function TriggerPopover({ info }: { info: Presentation }) {
  return <div className="np-rule-popover-content">
    <div className="np-rule-popover-heading">本次触发的规则</div>
    {!info.ready ? <div className="np-rule-popover-empty"><ExclamationCircleOutlined /> 暂无本次规则分析结果</div> :
      info.signals.length ? <div className="np-rule-popover-list">
        {info.signals.map((signal) => <div key={signal.code} className="np-rule-popover-item">
          <div className={`np-rule-popover-item-title tone-${signal.tone}`}>
            {signalIcon(signal)}<strong>{signal.title}</strong>
          </div>
          <div className="np-rule-popover-item-description">{signal.explanation}</div>
        </div>)}
      </div> : <div className="np-rule-popover-empty"><CheckCircleOutlined /> 本次未触发规则</div>}
    {info.ready && (info.period || info.asOf || info.ruleVersion) &&
      <div className="np-rule-popover-footer">
        {info.period && <span>观察期：{info.period}</span>}
        {info.asOf && <span>数据截止：{info.asOf}</span>}
        {info.ruleVersion && <span>规则：{info.ruleVersion}</span>}
      </div>}
  </div>;
}
export function TrackingSystemRecommendation({ product }: { product: Product }) {
  const info = presentationFor(product);
  if (!info.ready) return <span className="np-rule-no-snapshot">—</span>;
  return <div className="np-rule-recommendation">
    <Tag className={`np-rule-recommendation-tag np-rule-recommendation--${adviceTone[info.recommendation]}`}>
      {adviceText[info.recommendation]}
    </Tag>
  </div>;
}
export function TrackingTriggeredRules({ product }: { product: Product }) {
  const info = presentationFor(product);
  const first = info.signals[0]?.title;
  const rest = Math.max(0, info.signals.length - 1);
  const summary = !info.ready ? "—" : !first ? "暂无触发" : `${first}${rest ? ` +${rest}` : ""}`;
  if (!info.ready) return <span className="np-rule-no-snapshot">—</span>;
  return <div className="np-rule-trigger-cell">
    <span className="np-rule-trigger-summary" title={summary}>{summary}</span>
    <Popover
      trigger="hover"
      placement="topRight"
      mouseEnterDelay={0.1}
      overlayClassName="np-rule-popover-overlay"
      content={<TriggerPopover info={info} />}
      getPopupContainer={() => document.body}
    >
      <span className="np-rule-trigger-info" role="button" tabIndex={0} aria-label="查看本次触发的规则">
        <InfoCircleOutlined />
      </span>
    </Popover>
  </div>;
}
