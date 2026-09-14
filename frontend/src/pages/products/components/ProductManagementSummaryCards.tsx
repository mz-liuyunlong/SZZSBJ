import {
  AppstoreOutlined,
  CheckOutlined,
  GoldenFilled,
  PartitionOutlined,
  PlayCircleFilled,
} from "@ant-design/icons";
import type { ProductManagementSummary } from "@/pages/products/productManagementTypes";
import type { ReactNode } from "react";

interface ProductManagementSummaryCardsProps {
  total: number;
  summary: ProductManagementSummary;
}

function ProductManagementSummaryCards({
  total,
  summary,
}: ProductManagementSummaryCardsProps) {
  const cards: Array<{
    key: string;
    label: string;
    value: string;
    hint: string;
    icon: ReactNode;
    tone: string;
  }> = [
    {
      key: "total",
      label: "产品总数",
      value: total.toLocaleString(),
      hint: "当前筛选范围",
      icon: <AppstoreOutlined aria-hidden="true" />,
      tone: "blue",
    },
    {
      key: "synced",
      label: "已同步详情",
      value: summary.syncedDetailCount.toLocaleString(),
      hint: "已有 ProductInfo current",
      icon: <PlayCircleFilled aria-hidden="true" />,
      tone: "green",
    },
    {
      key: "completeness",
      label: "资料完整率",
      value: `${summary.dataCompletenessRate.toFixed(1)}%`,
      hint: "平均资料完整度",
      icon: <GoldenFilled aria-hidden="true" />,
      tone: "orange",
    },
    {
      key: "images",
      label: "已有图片",
      value: summary.withImageCount.toLocaleString(),
      hint: "至少一张来源图片",
      icon: <PartitionOutlined aria-hidden="true" />,
      tone: "purple",
    },
    {
      key: "tags",
      label: "已有标签",
      value: summary.withSourceTagCount.toLocaleString(),
      hint: "至少一个来源标签",
      icon: <CheckOutlined aria-hidden="true" />,
      tone: "green",
    },
    {
      key: "incomplete",
      label: "未补全资料",
      value: summary.incompleteCount.toLocaleString(),
      hint: "完整度低于 100%",
      icon: <PartitionOutlined aria-hidden="true" />,
      tone: "blue",
    },
  ];

  return (
    <div className="product-management__summary" aria-label="产品管理统计">
      {cards.map((card) => (
        <div
          key={card.key}
          className={[
            "product-management__summary-card",
            `product-management__summary-card--${card.tone}`,
          ].filter(Boolean).join(" ")}
        >
          <div className="product-management__summary-icon">{card.icon}</div>
          <div>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <small>{card.hint}</small>
          </div>
        </div>
      ))}
    </div>
  );
}

export default ProductManagementSummaryCards;
