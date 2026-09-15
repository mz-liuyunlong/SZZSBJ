import type { KeyboardEvent, ReactNode } from "react";
import type {
  ProductManagementIssueCode,
  ProductManagementSummary,
} from "@/pages/products/productManagementTypes";

interface ProductManagementSummaryCardsProps {
  summary: ProductManagementSummary;
  activeIssue?: ProductManagementIssueCode;
  onIssueChange: (issueCode?: ProductManagementIssueCode) => void;
}

interface SummaryCardItem {
  key: "total" | ProductManagementIssueCode;
  issueCode?: ProductManagementIssueCode;
  title: string;
  value: number;
  hint: string;
  icon: ReactNode;
}

const numberFormatter = new Intl.NumberFormat("zh-CN");

export default function ProductManagementSummaryCards({
  summary,
  activeIssue,
  onIssueChange,
}: ProductManagementSummaryCardsProps) {
  const cards: SummaryCardItem[] = [
    {
      key: "total",
      title: "产品总数",
      value: summary.total,
      hint: "当前基础筛选范围",
      icon: "品",
    },
    {
      key: "missing_purchase_cost",
      issueCode: "missing_purchase_cost",
      title: "缺采购价",
      value: summary.missingPurchaseCostCount,
      hint: "采购价为空或无效",
      icon: "价",
    },
    {
      key: "missing_purchase_delivery",
      issueCode: "missing_purchase_delivery",
      title: "缺采购交期",
      value: summary.missingPurchaseDeliveryCount,
      hint: "采购交期为空",
      icon: "期",
    },
    {
      key: "missing_package_dimensions",
      issueCode: "missing_package_dimensions",
      title: "缺尺寸",
      value: summary.missingPackageDimensionsCount,
      hint: "包装长宽高任一缺失",
      icon: "尺",
    },
    {
      key: "missing_image",
      issueCode: "missing_image",
      title: "缺图片",
      value: summary.missingImageCount,
      hint: "无可用商品图片",
      icon: "图",
    },
    {
      key: "missing_gross_weight",
      issueCode: "missing_gross_weight",
      title: "缺重量",
      value: summary.missingGrossWeightCount,
      hint: "商品毛重为空或无效",
      icon: "重",
    },
  ];

  const choose = (issueCode?: ProductManagementIssueCode) => {
    onIssueChange(issueCode && issueCode === activeIssue ? undefined : issueCode);
  };

  const onKeyDown = (
    event: KeyboardEvent<HTMLElement>,
    issueCode?: ProductManagementIssueCode,
  ) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    choose(issueCode);
  };

  return (
    <section className="product-management__summary-cards" aria-label="产品管理统计">
      {cards.map((card) => {
        const selected = card.issueCode ? card.issueCode === activeIssue : !activeIssue;
        return (
          <article
            key={card.key}
            className={`product-management__summary-card${selected ? " product-management__summary-card--active" : ""}`}
            role="button"
            tabIndex={0}
            aria-pressed={selected}
            aria-label={`${card.title}：${numberFormatter.format(card.value)}`}
            onClick={() => choose(card.issueCode)}
            onKeyDown={(event) => onKeyDown(event, card.issueCode)}
          >
            <div className="product-management__summary-icon">{card.icon}</div>
            <div className="product-management__summary-content">
              <span className="product-management__summary-title">{card.title}</span>
              <strong className="product-management__summary-value">
                {numberFormatter.format(card.value)}
              </strong>
              <span className="product-management__summary-hint">{card.hint}</span>
            </div>
          </article>
        );
      })}
    </section>
  );
}
