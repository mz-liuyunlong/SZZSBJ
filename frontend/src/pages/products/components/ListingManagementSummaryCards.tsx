import {
  AppstoreOutlined,
  CheckOutlined,
  CloseOutlined,
  PauseOutlined,
  ShoppingCartOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import type { ListingManagementRow } from "@/pages/products/listingManagementData";
import type { ReactNode } from "react";

export type ListingManagementSummaryCardKey = "total" | "online" | "offline" | "buybox" | "resold" | "disabled";

interface ListingManagementSummaryCardsProps {
  rows: ListingManagementRow[];
  activeKey?: ListingManagementSummaryCardKey;
  onCardClick?: (key: ListingManagementSummaryCardKey) => void;
}

function ListingManagementSummaryCards({
  rows,
  activeKey = "total",
  onCardClick,
}: ListingManagementSummaryCardsProps) {
  const total = rows.length;
  const online = rows.filter((row) => row.listingStatus === "在线").length;
  const offline = rows.filter((row) => row.listingStatus === "离线").length;
  const noBuyBox = rows.filter((row) => row.buyBoxStatus === "未拥有").length;
  const resold = rows.filter((row) => row.resold === "是").length;
  const disabled = rows.filter((row) => row.productStatus === "停用").length;

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
      label: "Listing总数",
      value: total.toLocaleString(),
      hint: "当前筛选结果",
      icon: <AppstoreOutlined aria-hidden="true" />,
      tone: "blue",
    },
    {
      key: "online",
      label: "在线Listing",
      value: online.toLocaleString(),
      hint: "点击查看在线",
      icon: <CheckOutlined aria-hidden="true" />,
      tone: "green",
    },
    {
      key: "offline",
      label: "离线Listing",
      value: offline.toLocaleString(),
      hint: "点击查看离线",
      icon: <CloseOutlined aria-hidden="true" />,
      tone: "red",
    },
    {
      key: "buybox",
      label: "未拥有购物车",
      value: noBuyBox.toLocaleString(),
      hint: "点击查看Buy Box风险",
      icon: <ShoppingCartOutlined aria-hidden="true" />,
      tone: "orange",
    },
    {
      key: "resold",
      label: "被跟卖",
      value: resold.toLocaleString(),
      hint: "点击查看跟卖",
      icon: <SwapOutlined aria-hidden="true" />,
      tone: "purple",
    },
    {
      key: "disabled",
      label: "停用产品",
      value: disabled.toLocaleString(),
      hint: "点击查看停用",
      icon: <PauseOutlined aria-hidden="true" />,
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
