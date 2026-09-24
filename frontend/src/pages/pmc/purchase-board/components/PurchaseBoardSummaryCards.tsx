/** Seven purchase-board stat cards (business rules v4 §9); clicking a card applies a filter. */
import ManagementStatCards, {
  type ManagementStatCardItem,
} from "@/components/report-table/ManagementStatCards";
import type { PurchaseBoardSummary } from "@/pages/pmc/purchase-board/purchaseBoardTypes";

export type PurchaseBoardCardKey =
  | "awaiting_arrival"
  | "arrival_overdue"
  | "purchase_overdue"
  | "average_cycle"
  | "month_amount"
  | "unstable_sku"
  | "itemid_pending";

interface PurchaseBoardSummaryCardsProps {
  summary?: PurchaseBoardSummary;
  activeKey?: PurchaseBoardCardKey;
  onCardClick: (key: PurchaseBoardCardKey) => void;
}

function OrdersIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 4h14v16H5zM8 9h8M8 13h8M8 17h5" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3 2.5 20h19L12 3ZM12 10v4M12 17v.5" />
    </svg>
  );
}

function MoneyIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3v18M16.5 7.2c0-1.5-1.8-2.7-4.2-2.7S8 5.7 8 7.2s1.5 2.4 4.3 3c2.8.6 4.2 1.5 4.2 3.3s-1.8 3-4.5 3-4.8-1.3-4.8-3" />
    </svg>
  );
}

function WaveIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 15c2-4 4-4 6 0s4 4 6 0 4-4 6 0" />
    </svg>
  );
}

function TagIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 12V4h8l10 10-8 8L3 12Z" />
      <circle cx="7.5" cy="8.5" r="1.5" />
    </svg>
  );
}

const currencySymbol: Record<string, string> = { CNY: "¥", USD: "$" };

const formatMonthAmount = (summary?: PurchaseBoardSummary) => {
  if (!summary || summary.monthPurchaseAmount.length === 0) return "—";
  return summary.monthPurchaseAmount
    .map(({ currencyCode, amount }) => {
      const symbol = currencyCode ? currencySymbol[currencyCode] ?? `${currencyCode} ` : "";
      return `${symbol}${amount.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
    })
    .join(" / ");
};

const formatDays = (value: number | null | undefined) => (
  value === null || value === undefined ? "—" : `${value.toFixed(1)} 天`
);

function buildPurchaseBoardCards(
  summary?: PurchaseBoardSummary,
): ManagementStatCardItem<PurchaseBoardCardKey>[] {
  const value = (pick: (data: PurchaseBoardSummary) => number) => (summary ? pick(summary) : "—");
  return [
    {
      key: "awaiting_arrival",
      title: "待到货采购单",
      subtitle: "已下单未到货 + 部分到货（去重单号）",
      value: value((data) => data.awaitingArrivalOrders),
      tone: "normal",
      icon: <OrdersIcon />,
    },
    {
      key: "arrival_overdue",
      title: "逾期未到货",
      subtitle: "到货逾期（S3 / S4）采购单",
      value: value((data) => data.arrivalOverdueOrders),
      tone: "danger",
      icon: <AlertIcon />,
    },
    {
      key: "purchase_overdue",
      title: "待采购超时",
      subtitle: summary
        ? `待下单采购单 ${summary.purchaseOverdueOrders} · 未转单计划 ${summary.purchaseOverduePlans}`
        : "待下单采购单 · 未转单计划",
      value: summary ? summary.purchaseOverdueOrders + summary.purchaseOverduePlans : "—",
      tone: "warning",
      icon: <ClockIcon />,
    },
    {
      key: "average_cycle",
      title: "平均采购交期",
      subtitle: "近 90 天到货采购单，按单取值",
      value: formatDays(summary?.averagePurchaseCycleDays90d),
      tone: "normal",
      icon: <ClockIcon />,
    },
    {
      key: "month_amount",
      title: "本月采购金额",
      subtitle: "本月下单明细分配金额，按币种、不折算",
      value: formatMonthAmount(summary),
      tone: "normal",
      icon: <MoneyIcon />,
    },
    {
      key: "unstable_sku",
      title: "交期不稳定 SKU",
      subtitle: "近 5 样本极差超阈值",
      value: value((data) => data.unstableSkuCount),
      tone: "warning",
      icon: <WaveIcon />,
    },
    {
      key: "itemid_pending",
      title: "ItemID 待处理",
      subtitle: summary
        ? `待打包单 / 未归属明细 · 未归属店铺 ${summary.unattributedStoreLines}`
        : "待打包单 / 未归属明细",
      value: value((data) => data.itemidPendingLines),
      tone: "warning",
      icon: <TagIcon />,
    },
  ];
}

function PurchaseBoardSummaryCards({
  summary,
  activeKey,
  onCardClick,
}: PurchaseBoardSummaryCardsProps) {
  return (
    <ManagementStatCards<PurchaseBoardCardKey>
      ariaLabel="采购看板统计"
      className="purchase-board__summary"
      cards={buildPurchaseBoardCards(summary)}
      activeKey={activeKey ?? ("" as PurchaseBoardCardKey)}
      onCardClick={onCardClick}
    />
  );
}

export default PurchaseBoardSummaryCards;
