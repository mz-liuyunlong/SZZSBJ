import type { ReactNode } from "react";
import ManagementStatCards, {
  type ManagementStatCardItem,
} from "@/components/report-table/ManagementStatCards";
import type { ListingManagementSummary } from "@/pages/products/listingManagementApi";

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

function ListingIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="5" y="4" width="14" height="16" rx="2" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </svg>
  );
}

function OnlineIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m5 12 4 4L19 6" />
    </svg>
  );
}

function CartIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 5h2l2 10h9l2-7H7" />
      <circle cx="10" cy="19" r="1.5" />
      <circle cx="17" cy="19" r="1.5" />
    </svg>
  );
}

function RatingIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m12 4 2.3 4.7 5.2.8-3.8 3.7.9 5.2L12 16l-4.6 2.4.9-5.2-3.8-3.7 5.2-.8L12 4Z" />
    </svg>
  );
}

function ResoldIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 7h9l-2.5-2.5M17 17H8l2.5 2.5" />
      <path d="M17 7a6 6 0 0 1 1.5 4M7 17a6 6 0 0 1-1.5-4" />
    </svg>
  );
}

function StrikeIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h14" />
      <path d="M7 7h10M9 17h6" />
      <path d="M8 4h8a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
    </svg>
  );
}

const icon = (node: ReactNode) => node;

const cardsFromSummary = (
  summary: ListingManagementSummary,
): ManagementStatCardItem<ListingManagementSummaryCardKey>[] => [
  {
    key: "total",
    title: "Listing概览",
    ariaLabel: "Listing总数",
    subtitle: "当前Listing整体状态",
    value: summary.total,
    tone: "normal",
    icon: icon(<ListingIcon />),
  },
  {
    key: "online",
    title: "在售商品",
    ariaLabel: "在售商品",
    subtitle: "当前正常在售数量",
    value: summary.online,
    tone: "success",
    icon: icon(<OnlineIcon />),
  },
  {
    key: "buybox",
    title: "购物车异常",
    ariaLabel: "购物车异常",
    subtitle: "购物车丢失或异常",
    value: summary.buyboxException,
    tone: "danger",
    icon: icon(<CartIcon />),
  },
  {
    key: "rating",
    title: "评分预警",
    ariaLabel: "评分预警",
    subtitle: "评分低于预警值",
    value: summary.ratingWarning,
    tone: "warning",
    icon: icon(<RatingIcon />),
  },
  {
    key: "resold",
    title: "跟卖预警",
    ariaLabel: "跟卖预警",
    subtitle: "发现疑似跟卖商品",
    value: summary.resoldWarning,
    tone: "danger",
    icon: icon(<ResoldIcon />),
  },
  {
    key: "strike",
    title: "划线价异常",
    ariaLabel: "划线价异常",
    subtitle: "划线价失效或异常",
    value: summary.strikePriceException,
    tone: "warning",
    icon: icon(<StrikeIcon />),
  },
];

function ListingManagementSummaryCards({
  summary,
  activeKey = "total",
  onCardClick,
}: ListingManagementSummaryCardsProps) {
  return (
    <ManagementStatCards
      ariaLabel="Listing管理统计"
      className="listing-management__summary-cards"
      cards={cardsFromSummary(summary)}
      activeKey={activeKey}
      onCardClick={(key) => onCardClick?.(key)}
    />
  );
}

export default ListingManagementSummaryCards;
