import {
  AppstoreOutlined,
  CheckOutlined,
  ShoppingCartOutlined,
  StarOutlined,
  SwapOutlined,
  TagOutlined,
} from "@ant-design/icons";
import type { ListingManagementSummary } from "@/pages/products/listingManagementApi";
import type { ReactNode } from "react";

export type ListingManagementSummaryCardKey =
  | "total"
  | "online"
  | "buybox"
  | "rating"
  | "resold"
  | "strike";

interface ListingManagementSummaryCardsProps {
  summary: ListingManagementSummary;
  activeKey?: ListingManagementSummaryCardKey;
  onCardClick?: (key: ListingManagementSummaryCardKey) => void;
}

function ListingManagementSummaryCards({
  summary,
  activeKey = "total",
  onCardClick,
}: ListingManagementSummaryCardsProps) {
  const cards: Array<{
    key: ListingManagementSummaryCardKey;
    label: string;
    value: string;
    hint: string;
    icon: ReactNode;
    tone: string;
  }> = [
    {
      key: "total",
      label: "Listing概览",
      value: summary.total.toLocaleString(),
      hint: "当前Listing整体状态",
      icon: <AppstoreOutlined aria-hidden="true" />,
      tone: "blue",
    },
    {
      key: "online",
      label: "在售商品",
      value: summary.online.toLocaleString(),
      hint: "当前正常在售数量",
      icon: <CheckOutlined aria-hidden="true" />,
      tone: "green",
    },
    {
      key: "buybox",
      label: "购物车异常",
      value: summary.buyboxException.toLocaleString(),
      hint: "购物车丢失或异常",
      icon: <ShoppingCartOutlined aria-hidden="true" />,
      tone: "red",
    },
    {
      key: "rating",
      label: "评分预警",
      value: summary.ratingWarning.toLocaleString(),
      hint: "评分低于预警值",
      icon: <StarOutlined aria-hidden="true" />,
      tone: "orange",
    },
    {
      key: "resold",
      label: "跟卖预警",
      value: summary.resoldWarning.toLocaleString(),
      hint: "发现疑似跟卖商品",
      icon: <SwapOutlined aria-hidden="true" />,
      tone: "purple",
    },
    {
      key: "strike",
      label: "划线价异常",
      value: summary.strikePriceException.toLocaleString(),
      hint: "划线价失效或异常",
      icon: <TagOutlined aria-hidden="true" />,
      tone: "gray",
    },
  ];

  return (
    <div className="listing-management__summary" aria-label="Listing 管理统计">
      {cards.map((card) => (
        <button
          key={card.key}
          type="button"
          className={[
            "listing-management__summary-card",
            `listing-management__summary-card--${card.tone}`,
            activeKey === card.key ? "listing-management__summary-card--active" : "",
          ].filter(Boolean).join(" ")}
          aria-pressed={activeKey === card.key}
          onClick={() => onCardClick?.(card.key)}
        >
          <div className="listing-management__summary-icon">{card.icon}</div>
          <div>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <small>{card.hint}</small>
          </div>
        </button>
      ))}
    </div>
  );
}

export default ListingManagementSummaryCards;
