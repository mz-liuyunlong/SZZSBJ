import { ArrowDownOutlined, ArrowUpOutlined } from "@ant-design/icons";
import { Card } from "antd";
import type { CSSProperties, ReactNode } from "react";
import "@/components/report-table/reportTable.css";

export type ReportSummaryTone = "blue" | "green" | "orange" | "purple" | "red" | "cyan";
export type ReportSummaryTrendDirection = "up" | "down" | "cost-up";

export interface ReportSummaryMetric {
  title: string;
  value: number | null;
  formatter: (value: number | null) => string;
  subtitle: string;
  icon: ReactNode;
  tone: ReportSummaryTone;
  trend?: string | null;
  trendDirection?: ReportSummaryTrendDirection | null;
}

interface ReportSummaryCardsProps {
  ariaLabel: string;
  className?: string;
  metrics: ReportSummaryMetric[];
}

function ReportSummaryCards({
  ariaLabel,
  className,
  metrics,
}: ReportSummaryCardsProps) {
  return (
    <section
      className={["report-summary-cards", className].filter(Boolean).join(" ")}
      aria-label={ariaLabel}
    >
      {metrics.map((metric, index) => (
        <Card
          key={metric.title}
          size="small"
          className={[
            "report-summary-card",
            `report-summary-card--${metric.tone}`,
            metric.trendDirection ? `report-summary-card--trend-${metric.trendDirection}` : "",
          ].filter(Boolean).join(" ")}
          style={{ "--summary-card-index": index } as CSSProperties}
        >
          <span
            className={[
              "report-summary-card__rising",
              metric.trendDirection ? `report-summary-card__rising--${metric.trendDirection}` : "",
            ].filter(Boolean).join(" ")}
            aria-hidden="true"
          >
            <span />
            <span />
            <span />
          </span>
          <span className="report-summary-card__icon" aria-hidden="true">
            {metric.icon}
          </span>
          <span className="report-summary-card__content">
            <span className="report-summary-card__title">{metric.title}</span>
            <strong className="report-summary-card__value">
              {metric.formatter(metric.value)}
            </strong>
            <span className="report-summary-card__subtitle">{metric.subtitle}</span>
          </span>
          {metric.trend && metric.trendDirection && (
            <span
              className={[
                "report-summary-card__comparison",
                `report-summary-card__comparison--${metric.trendDirection}`,
              ].join(" ")}
            >
              <span className="report-summary-card__trend">
                {metric.trendDirection === "down" ? <ArrowDownOutlined /> : <ArrowUpOutlined />}
                {metric.trend}
              </span>
            </span>
          )}
        </Card>
      ))}
    </section>
  );
}

export default ReportSummaryCards;
