import {
  AppstoreOutlined,
  CheckOutlined,
  GoldenFilled,
  PartitionOutlined,
  PlayCircleFilled,
} from "@ant-design/icons";
import type { ProductManagementRow } from "@/pages/products/productManagementTypes";

interface ProductManagementSummaryCardsProps {
  rows: ProductManagementRow[];
}

function ProductManagementSummaryCards({ rows }: ProductManagementSummaryCardsProps) {
  const total = rows.length;
  const gradeA = rows.filter((row) => row.productGrade === "A级").length;
  const gradeB = rows.filter((row) => row.productGrade === "B级").length;
  const gradeC = rows.filter((row) => row.productGrade === "C级").length;
  const completeness = total > 0
    ? rows.reduce((sum, row) => sum + row.dataCompleteness, 0) / total
    : 0;
  const linkedPlatformSkuCount = rows.reduce((sum, row) => sum + row.linkedPlatformSkuCount, 0);

  const cards = [
    {
      key: "total",
      label: "产品总数",
      value: total.toLocaleString(),
      hint: "SKU基础数据",
      icon: <AppstoreOutlined aria-hidden="true" />,
      tone: "blue",
    },
    {
      key: "gradeA",
      label: "A级产品",
      value: gradeA.toLocaleString(),
      hint: "核心基础资料",
      icon: <PlayCircleFilled aria-hidden="true" />,
      tone: "green",
    },
    {
      key: "gradeB",
      label: "B级产品",
      value: gradeB.toLocaleString(),
      hint: "常规维护",
      icon: <GoldenFilled aria-hidden="true" />,
      tone: "orange",
    },
    {
      key: "gradeC",
      label: "C级产品",
      value: gradeC.toLocaleString(),
      hint: "待后续治理",
      icon: <PartitionOutlined aria-hidden="true" />,
      tone: "purple",
    },
    {
      key: "complete",
      label: "资料完整率",
      value: `${completeness.toFixed(1)}%`,
      hint: "基础字段完整",
      icon: <CheckOutlined aria-hidden="true" />,
      tone: "green",
    },
    {
      key: "linked",
      label: "已关联平台SKU",
      value: linkedPlatformSkuCount.toLocaleString(),
      hint: "多平台映射",
      icon: <PartitionOutlined aria-hidden="true" />,
      tone: "blue",
    },
  ];

  return (
    <div className="product-management__summary" aria-label="产品管理统计">
      {cards.map((card) => (
        <div key={card.key} className={`product-management__summary-card product-management__summary-card--${card.tone}`}>
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
