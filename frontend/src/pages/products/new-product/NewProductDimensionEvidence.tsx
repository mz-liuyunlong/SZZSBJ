import type { Product } from "./nativeData";
// PR337_CORRECTION_POPOVER_V7: local scoring request panel.
import NewProductCorrectionPopover from "./NewProductCorrectionPopover";
import {
  adResult,
  profitResult,
  speedResult,
  trustResult,
  type ScoringFacts,
  type ScoringParameters,
} from "./NewProductConfirmedScoring";

type Dimension = "speed" | "ad" | "profit" | "trust";

type Props = {
  product: Product;
  dimension: Dimension;
  parameters: ScoringParameters;
  loaded: boolean;
  currentVersion: number;
  readOnly?: boolean;
  onRequestCorrection: (requestedScore:number, reason:string) => Promise<{ok:boolean;error?:string}> | {ok:boolean;error?:string};
};

const num = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "" || typeof v === "boolean") {
    return null;
  }
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const fmt = (v: unknown): string => {
  const n = num(v);
  return n === null ? "—" : n.toFixed(2);
};

const fmtRaw = (v: unknown): string => {
  if (v === null || v === undefined || v === "") return "—";
  return String(v).replace(/-?\d+\.\d+/g, (m) => {
    const n = Number(m);
    return Number.isFinite(n) ? n.toFixed(2) : m;
  });
};

/** Presentation only: exact scoring inputs, saved score and weights are unchanged. */
export default function NewProductDimensionEvidence({
  product,
  dimension,
  parameters,
  loaded,
  currentVersion,
  readOnly=false,
  onRequestCorrection,
}: Props) {
  const ruleText =
    dimension === "speed"
      ? `首单≤${parameters.speed.firstFullDays}天满分，≥${parameters.speed.firstZeroDays}天零分；14天订单目标${parameters.speed.targetOrders}单。`
      : dimension === "ad"
        ? "按 ACOS / CPC / CVR 三项评分后加权汇总。"
        : dimension === "profit"
          ? "按 ROI / 毛利率 两项评分后加权汇总。"
          : "按累计销售件数 / 订单件数比 两项评分后加权汇总。";

  const currentScore = product.backend
    ? num(product.backend.evaluation.dimensions[dimension])
    : num(product.overrides?.[dimension] ?? product.scores[dimension]);

  const footer = (
    <div className="np-evidence-visual-footer">
      <div className="np-evidence-visual-explanation">
        <span className="np-evidence-visual-info-icon" aria-hidden="true">i</span>
        <span>{ruleText}</span>
      </div>
      {!readOnly && <NewProductCorrectionPopover
        dimension={dimension}
        currentScore={currentScore}
        readOnly={readOnly}
        onSubmit={onRequestCorrection}
      >
        <button type="button" className="btn small np-evidence-visual-correction">
          修正分数
        </button>
      </NewProductCorrectionPopover>}
    </div>
  );

  const unavailable = (message: string) => (
    <div className="np-evidence-visual">
      <div className="np-evidence-visual-content">
        <p className="np-evidence-visual-unavailable">{message}</p>
      </div>
      {footer}
    </div>
  );

  const backend = product.backend as
    | (NonNullable<Product["backend"]> & {
        scoringFacts?: Record<string, unknown>;
      })
    | undefined;

  if (!backend) {
    return unavailable("暂无真实评分计算明细");
  }

  if (product.tracking === "打品成功" || product.tracking === "打品失败") {
    return unavailable("该商品已闭环，沿用闭环时评分快照。");
  }

  if (!loaded || backend.ruleVersion !== currentVersion) {
    return unavailable("规则版本未确认，暂不展示计算明细。");
  }

  const raw = backend.scoringFacts;
  if (!raw) {
    return unavailable("缺少评分原始数据，暂不展示计算明细。");
  }

  const facts: ScoringFacts = {
    firstOrderDay: num(raw.first_order_day),
    elapsedDays: num(raw.elapsed_days),
    ordersInWindow: num(raw.effective_orders_14d ?? raw.valid_orders_14d),
    adStatus:
      raw.ad_status === "active" || raw.ad_status === "not_run"
        ? raw.ad_status
        : "unknown",
    adClicks: num(raw.ad_clicks),
    adSpend: num(raw.ad_spend_usd),
    adOrders: num(raw.ad_orders),
    adRevenue: num(raw.ad_revenue_usd),
    roi: num(raw.roi),
    grossMarginPct: num(raw.gross_margin_pct),
    validSoldUnits: num(raw.valid_units_14d),
    validOrders: num(raw.valid_orders_14d),
    singleUnitOrders: null,
    trustOrderUnitsRatioPct: num(raw.trust_order_units_ratio_pct),
    marketScore: num(raw.market_score),
  };

  let calculation:
    | ReturnType<typeof speedResult>
    | ReturnType<typeof adResult>
    | ReturnType<typeof profitResult>
    | ReturnType<typeof trustResult>;

  try {
    calculation =
      dimension === "speed"
        ? speedResult(facts, parameters)
        : dimension === "ad"
          ? adResult(facts, parameters)
          : dimension === "profit"
            ? profitResult(facts, parameters)
            : trustResult(facts, parameters);
  } catch {
    return unavailable("评分计算异常，暂不展示计算明细。");
  }

  const details = calculation.details ?? [];
  const weights =
    dimension === "speed"
      ? [parameters.speed.firstWeight, parameters.speed.ordersWeight]
      : dimension === "ad"
        ? [parameters.ad.acosWeight, parameters.ad.cpcWeight, parameters.ad.cvrWeight]
        : dimension === "profit"
          ? [parameters.profit.roiWeight, parameters.profit.marginWeight]
          : [parameters.trust.unitsWeight, parameters.trust.singleRatioWeight];

  const stored = num(backend.evaluation.dimensions[dimension]);
  const recalculated = num(calculation.score);
  const usable =
    details.length === weights.length &&
    details.length > 0 &&
    details.every((x) => x.score !== null && x.score !== undefined);

  if (!usable) {
    const zero = raw.zero_sales_verified === true;
    if (zero && stored === 0) {
      return unavailable("已核实14天零销量：按零销量规则计0分，未伪造ROI或广告指标。");
    }
    const lack = calculation.missing?.filter(Boolean) ?? [];
    return unavailable(lack.length
      ? `缺失评分证据：${lack.join("、")}`
      : "同一次评分的原始指标尚未齐备，请检查已保存证据。");
  }

  const parts = details.map((x, i) => Number(x.score) * weights[i] / 100);
  const mismatch =
    stored !== null &&
    recalculated !== null &&
    Math.abs(stored - recalculated) > 0.02;

  return (
    <div className="np-evidence-visual">
      <div className="np-evidence-visual-content">
        {dimension === "speed" ? (
          <div className="np-evidence-visual-speed-grid">
            {details.map((x, i) => (
              <div className="np-evidence-visual-speed-item" key={i}>
                <div className="np-evidence-visual-speed-summary">
                  <span className="np-evidence-visual-chip">{x.name}</span>
                  <strong className="np-evidence-visual-raw">{fmtRaw(x.raw)}</strong>
                </div>
                <div className="np-evidence-visual-speed-math">
                  <span>{fmt(x.score)} × {weights[i]}% = </span>
                  <strong className="np-evidence-visual-result">{fmt(parts[i])}</strong>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="np-evidence-visual-rows">
            {details.map((x, i) => (
              <div className="np-evidence-visual-row" key={i}>
                <div className="np-evidence-visual-metric">
                  <span className="np-evidence-visual-chip">{x.name}</span>
                  <span className="np-evidence-visual-dot" aria-hidden="true">·</span>
                  <strong className="np-evidence-visual-raw">{fmtRaw(x.raw)}</strong>
                </div>
                <div className="np-evidence-visual-math">
                  <span>{fmt(x.score)} × {weights[i]}% = </span>
                  <strong className="np-evidence-visual-result">{fmt(parts[i])}</strong>
                </div>
              </div>
            ))}
          </div>
        )}
        {mismatch ? (
          <div className="np-evidence-visual-warning">
            当前展示分数 {fmt(stored)}，按现规则反算 {fmt(recalculated)}。
          </div>
        ) : null}
      </div>
      {footer}
    </div>
  );
}
