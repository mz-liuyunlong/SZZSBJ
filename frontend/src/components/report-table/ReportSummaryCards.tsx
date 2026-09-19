import { Card, Tooltip } from "antd";
import type { CSSProperties, ReactNode } from "react";
import "@/components/report-table/reportTable.css";

export type ReportSummaryTrendDirection = "up" | "down" | "flat";
export type ReportSummaryTrendTone = "good" | "bad" | "neutral";

export interface ReportSummaryMetricComparison {
  current: string;
  previous: string;
  change: string | null;
  direction: ReportSummaryTrendDirection;
  tone: ReportSummaryTrendTone;
  status: string;
}

export interface ReportSummaryMetric {
  label: string;
  value: string;
  comparison?: ReportSummaryMetricComparison | null;
}

export interface ReportSummaryCard {
  id: string;
  title: string;
  badge?: string;
  accent: string;
  metrics: [ReportSummaryMetric, ReportSummaryMetric];
}

interface ReportSummaryCardsProps {
  ariaLabel: string;
  cards: ReportSummaryCard[];
  className?: string;
}

const trendArrow = (direction: ReportSummaryTrendDirection) => {
  if (direction === "up") return "↑";
  if (direction === "down") return "↓";
  return "";
};

const trendText = (comparison: ReportSummaryMetricComparison) => {
  if (!comparison.change || comparison.direction === "flat") return "暂无对比";
  return `${trendArrow(comparison.direction)} ${comparison.change}`;
};

const trendAriaText = (
  metricLabel: string,
  comparison: ReportSummaryMetricComparison,
) => (
  `当前${metricLabel}：${comparison.current}，昨日${metricLabel}：${comparison.previous}，变化：${trendText(comparison)}，${comparison.status}`
);

function SummaryMetricTooltip({
  metricLabel,
  comparison,
}: {
  metricLabel: string;
  comparison: ReportSummaryMetricComparison;
}) {
  return (
    <div className="report-summary-tooltip report-summary-tooltip--compact">
      <div className="report-summary-tooltip__grid">
        <section className="report-summary-tooltip__item">
          <span className="report-summary-tooltip__label">当前{metricLabel}</span>
          <strong className="report-summary-tooltip__value">{comparison.current}</strong>
        </section>

        <section className="report-summary-tooltip__item">
          <span className="report-summary-tooltip__label">昨日{metricLabel}</span>
          <strong className="report-summary-tooltip__value">{comparison.previous}</strong>
        </section>

        <section className="report-summary-tooltip__item">
          <span className="report-summary-tooltip__label">变化</span>
          <strong
            className={[
              "report-summary-tooltip__change",
              `report-summary-tooltip__change--${comparison.tone}`,
            ].join(" ")}
          >
            {trendText(comparison)}
          </strong>
        </section>

        <section className="report-summary-tooltip__item">
          <span className="report-summary-tooltip__label">状态</span>
          <strong
            className={[
              "report-summary-tooltip__status",
              `report-summary-tooltip__status--${comparison.tone}`,
            ].join(" ")}
          >
            {comparison.status}
          </strong>
        </section>
      </div>
    </div>
  );
}

function renderTrendNode(
  metric: ReportSummaryMetric,
  comparison: ReportSummaryMetricComparison,
): ReactNode {
  return (
    <Tooltip
      title={(
        <SummaryMetricTooltip
          metricLabel={metric.label}
          comparison={comparison}
        />
      )}
      placement="top"
      classNames={{
        root: "report-summary-rich-tooltip report-summary-rich-tooltip--compact",
      }}
    >
      <span
        className={[
          "report-summary-pair-card__trend",
          `report-summary-pair-card__trend--${comparison.tone}`,
        ].join(" ")}
        aria-label={trendAriaText(metric.label, comparison)}
      >
        {comparison.change && comparison.direction !== "flat" ? (
          <>
            <i aria-hidden="true">{trendArrow(comparison.direction)}</i>
            {comparison.change}
          </>
        ) : (
          trendText(comparison)
        )}
      </span>
    </Tooltip>
  );
}

function ReportSummaryCards({
  ariaLabel,
  cards,
  className,
}: ReportSummaryCardsProps) {
  return (
    <section
      className={["report-summary-cards", className].filter(Boolean).join(" ")}
      aria-label={ariaLabel}
    >
      {cards.map((card, cardIndex) => (
        <Card
          key={card.id}
          size="small"
          className={[
            "report-summary-card",
            "report-summary-pair-card",
            `report-summary-pair-card--${card.id}`,
            cardIndex === 0 ? "report-summary-pair-card--edge-left" : "",
            cardIndex === cards.length - 1 ? "report-summary-pair-card--edge-right" : "",
          ].filter(Boolean).join(" ")}
          style={{ "--summary-accent": card.accent } as CSSProperties}
        >
          <span className="report-summary-pair-card__accent" aria-hidden="true" />
          <header className="report-summary-pair-card__head">
            <div className="report-summary-pair-card__title">{card.title}</div>
            <span className="report-summary-pair-card__badge">{card.badge ?? "较昨日"}</span>
          </header>
          <div className="report-summary-pair-card__dash" />
          <div className="report-summary-pair-card__metrics">
            {card.metrics.map((metric) => (
              <span
                key={metric.label}
                className="report-summary-pair-card__metric"
                tabIndex={0}
                aria-label={`${metric.label}：${metric.value}`}
              >
                <span className="report-summary-pair-card__value">{metric.value}</span>
                <span className="report-summary-pair-card__meta">
                  <span>{metric.label}</span>
                  {metric.comparison ? renderTrendNode(metric, metric.comparison) : null}
                </span>
              </span>
            ))}
          </div>
        </Card>
      ))}
    </section>
  );
}

export default ReportSummaryCards;
