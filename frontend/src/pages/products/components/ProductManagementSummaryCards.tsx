import type { ReactNode } from "react";
import ManagementStatCards, {
  type ManagementStatCardItem,
} from "@/components/report-table/ManagementStatCards";
import type {
  ProductManagementIssueCode,
  ProductManagementSummary,
} from "@/pages/products/productManagementTypes";

interface ProductManagementSummaryCardsProps {
  summary: ProductManagementSummary;
  activeIssue?: ProductManagementIssueCode;
  onIssueChange: (issueCode?: ProductManagementIssueCode) => void;
}

type ProductSummaryCardKey = "total" | ProductManagementIssueCode;

function ProductIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9Z" />
      <path d="m4.5 7.5 7.5 4 7.5-4M12 11.5V21" />
    </svg>
  );
}

function PriceIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3v18M16.5 7.2c0-1.5-1.8-2.7-4.2-2.7S8 5.7 8 7.2s1.5 2.4 4.3 3c2.8.6 4.2 1.5 4.2 3.3s-1.8 3-4.5 3-4.8-1.3-4.8-3" />
    </svg>
  );
}

function LeadIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}

function SizeIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 19 19 5M7 5H5v2M17 19h2v-2" />
      <path d="M9 5h3M5 9v3M12 19h3M19 12v3" />
    </svg>
  );
}

function ImageIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <circle cx="9" cy="10" r="1.5" />
      <path d="m5.5 17 4.2-4 3.2 3 2.2-2 3.4 3" />
    </svg>
  );
}

function WeightIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 8.5h10l2 11H5l2-11Z" />
      <path d="M9 8.5a3 3 0 0 1 6 0" />
      <path d="M12 11v3" />
    </svg>
  );
}

const icon = (node: ReactNode) => node;

const cardsFromSummary = (
  summary: ProductManagementSummary,
): ManagementStatCardItem<ProductSummaryCardKey>[] => [
  {
    key: "total",
    title: "产品概览",
    ariaLabel: "产品总数",
    subtitle: "系统内已建档产品数量",
    value: summary.total,
    tone: "normal",
    icon: icon(<ProductIcon />),
  },
  {
    key: "missing_purchase_cost",
    title: "价格待完善",
    ariaLabel: "缺采购价",
    subtitle: "尚未维护采购单价",
    value: summary.missingPurchaseCostCount,
    tone: "warning",
    icon: icon(<PriceIcon />),
  },
  {
    key: "missing_purchase_delivery",
    title: "交期待完善",
    ariaLabel: "缺采购交期",
    subtitle: "尚未维护采购交期",
    value: summary.missingPurchaseDeliveryCount,
    tone: "warning",
    icon: icon(<LeadIcon />),
  },
  {
    key: "missing_package_dimensions",
    title: "尺寸待完善",
    ariaLabel: "缺尺寸",
    subtitle: "缺少长 / 宽 / 高信息",
    value: summary.missingPackageDimensionsCount,
    tone: "danger",
    icon: icon(<SizeIcon />),
  },
  {
    key: "missing_image",
    title: "图片待完善",
    ariaLabel: "缺图片",
    subtitle: "缺少尺寸图片",
    value: summary.missingImageCount,
    tone: "danger",
    icon: icon(<ImageIcon />),
  },
  {
    key: "missing_gross_weight",
    title: "重量待完善",
    ariaLabel: "缺重量",
    subtitle: "尚未维护重量信息",
    value: summary.missingGrossWeightCount,
    tone: "warning",
    icon: icon(<WeightIcon />),
  },
];

export default function ProductManagementSummaryCards({
  summary,
  activeIssue,
  onIssueChange,
}: ProductManagementSummaryCardsProps) {
  const activeKey: ProductSummaryCardKey = activeIssue ?? "total";

  return (
    <ManagementStatCards
      ariaLabel="产品管理统计"
      className="product-management__summary-cards"
      cards={cardsFromSummary(summary)}
      activeKey={activeKey}
      onCardClick={(key) => {
        if (key === "total") {
          onIssueChange(undefined);
          return;
        }
        onIssueChange(key === activeIssue ? undefined : key);
      }}
    />
  );
}
