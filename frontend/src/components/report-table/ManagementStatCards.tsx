/** Clickable stat cards for management/board summaries; the active card doubles as a filter. */
import type { CSSProperties, KeyboardEvent, ReactNode } from "react";
import "@/components/report-table/ManagementStatCards.css";

export type ManagementStatTone = "normal" | "success" | "warning" | "danger";

export interface ManagementStatCardItem<Key extends string = string> {
  key: Key;
  title: string;
  ariaLabel?: string;
  subtitle: string;
  value: number | string;
  /** Shown under the number. Used by the leading layout. */
  unit?: string;
  /** Icon sits on the left; title, number, unit and subtitle stack on the right. */
  layout?: "leading";
  tone: ManagementStatTone;
  icon: ReactNode;
  accent?: string;
  glow?: string;
}

interface ManagementStatCardsProps<Key extends string> {
  ariaLabel: string;
  cards: ManagementStatCardItem<Key>[];
  activeKey: Key;
  className?: string;
  onCardClick: (key: Key) => void;
}

const numberFormatter = new Intl.NumberFormat("zh-CN");

const toneConfig: Record<ManagementStatTone, { accent: string; glow: string }> = {
  normal: {
    accent: "#2563eb",
    glow: "rgba(37, 99, 235, 0.07)",
  },
  success: {
    accent: "#2563eb",
    glow: "rgba(37, 99, 235, 0.07)",
  },
  warning: {
    accent: "#d97706",
    glow: "rgba(245, 158, 11, 0.08)",
  },
  danger: {
    accent: "#dc2626",
    glow: "rgba(239, 68, 68, 0.07)",
  },
};

const formatValue = (value: number | string) => (
  typeof value === "number" ? numberFormatter.format(value) : value
);

function ManagementStatCards<Key extends string>({
  ariaLabel,
  cards,
  activeKey,
  className,
  onCardClick,
}: ManagementStatCardsProps<Key>) {
  const handleKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    key: Key,
  ) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onCardClick(key);
  };

  return (
    <section
      className={["management-stat-cards", className].filter(Boolean).join(" ")}
      aria-label={ariaLabel}
    >
      {cards.map((card) => {
        const active = activeKey === card.key;
        const tone = toneConfig[card.tone];
        const shownValue = formatValue(card.value);
        const accessibleValue = card.unit && card.value !== "—" ? `${shownValue} ${card.unit}` : shownValue;

        return (
          <button
            key={card.key}
            className={[
              "management-stat-card",
              `management-stat-card--${card.tone}`,
              card.layout === "leading" ? "management-stat-card--leading" : "",
              active ? "is-active" : "",
            ].filter(Boolean).join(" ")}
            style={{
              "--management-stat-accent": card.accent ?? tone.accent,
              "--management-stat-glow": card.glow ?? tone.glow,
            } as CSSProperties}
            type="button"
            aria-pressed={active}
            aria-label={`${card.ariaLabel ?? card.title}：${accessibleValue}`}
            onClick={() => onCardClick(card.key)}
            onKeyDown={(event) => handleKeyDown(event, card.key)}
          >
            <span className="management-stat-card__visual" aria-hidden="true">
              {card.icon}
            </span>

            {card.layout === "leading" ? (
              <span className="management-stat-card__copy">
                <span className="management-stat-card__title">{card.title}</span>
                <span className="management-stat-card__value">{shownValue}</span>
                {card.unit && card.value !== "—" ? (
                  <span className="management-stat-card__unit">{card.unit}</span>
                ) : null}
                <span className="management-stat-card__subtitle">{card.subtitle}</span>
              </span>
            ) : (
              <>
                <span className="management-stat-card__content">
                  <span className="management-stat-card__title">{card.title}</span>
                  <span className="management-stat-card__subtitle">{card.subtitle}</span>
                </span>

                <span className="management-stat-card__value">
                  {shownValue}
                </span>
              </>
            )}
          </button>
        );
      })}
    </section>
  );
}

export default ManagementStatCards;
