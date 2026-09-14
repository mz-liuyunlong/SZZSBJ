import type { ReactNode } from "react";
import type { ProductManagementRow } from "@/pages/products/productManagementTypes";

interface ProductManagementSummaryCardsProps {
  rows?: ProductManagementRow[];
  total: number;
}

interface SummaryCardItem {
  key: string;
  title: string;
  value: number;
  hint: string;
  icon: ReactNode;
}

const numberFormatter = new Intl.NumberFormat("zh-CN");

const emptyTextValues = new Set([
  "",
  "-",
  "--",
  "暂无数据",
  "无法计算",
  "null",
  "undefined",
]);

const isFilledValue = (value: unknown): boolean => {
  if (value === null || value === undefined) return false;

  if (Array.isArray(value)) {
    return value.some(isFilledValue);
  }

  if (typeof value === "string") {
    return !emptyTextValues.has(value.trim());
  }

  if (typeof value === "number") {
    return Number.isFinite(value);
  }

  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "object") {
    return Object.values(value as Record<string, unknown>).some(isFilledValue);
  }

  return true;
};

const hasAnyField = (row: ProductManagementRow, keys: string[]) => {
  const record = row as unknown as Record<string, unknown>;
  return keys.some((key) => isFilledValue(record[key]));
};

const hasDimension = (row: ProductManagementRow) => {
  const record = row as unknown as Record<string, unknown>;

  const dimensionTextKeys = [
    "dimensions",
    "dimension",
    "packageDimensions",
    "packageDimension",
    "packageSize",
    "productDimensions",
    "productSize",
    "size",
  ];

  if (dimensionTextKeys.some((key) => isFilledValue(record[key]))) {
    return true;
  }

  const lengthKeys = ["length", "packageLength", "outerLength", "productLength"];
  const widthKeys = ["width", "packageWidth", "outerWidth", "productWidth"];
  const heightKeys = ["height", "packageHeight", "outerHeight", "productHeight"];

  return (
    lengthKeys.some((key) => isFilledValue(record[key])) &&
    widthKeys.some((key) => isFilledValue(record[key])) &&
    heightKeys.some((key) => isFilledValue(record[key]))
  );
};

const getImageCount = (row: ProductManagementRow) => {
  const record = row as unknown as Record<string, unknown>;
  const images = new Set<string>();

  const collect = (value: unknown) => {
    if (!isFilledValue(value)) return;

    if (Array.isArray(value)) {
      value.forEach(collect);
      return;
    }

    if (typeof value === "object" && value !== null) {
      Object.values(value as Record<string, unknown>).forEach(collect);
      return;
    }

    images.add(String(value).trim());
  };

  collect(record.images);
  collect(record.imageUrl);
  collect(record.image);
  collect(record.mainImageUrl);
  collect(record.mainImage);

  return images.size;
};

export default function ProductManagementSummaryCards({
  rows = [],
  total,
}: ProductManagementSummaryCardsProps) {
  const missingPurchasePrice = rows.filter((row) => !hasAnyField(row, [
    "purchasePrice",
    "productPurchasePrice",
    "procurementPrice",
    "purchaseCost",
    "costPrice",
    "basePurchasePrice",
    "productCost",
  ])).length;

  const missingDimension = rows.filter((row) => !hasDimension(row)).length;

  const missingPurchaseLeadTime = rows.filter((row) => !hasAnyField(row, [
    "purchaseLeadTime",
    "purchaseLeadDays",
    "purchaseCycle",
    "purchaseDeliveryTime",
    "purchaseDeliveryDays",
    "procurementLeadTime",
    "leadTime",
  ])).length;

  const missingImage = rows.filter((row) => getImageCount(row) < 2).length;

  const missingWeight = rows.filter((row) => !hasAnyField(row, [
    "weight",
    "packageWeight",
    "grossWeight",
    "netWeight",
    "shippingWeight",
    "productWeight",
    "packageActualWeight",
    "actualWeight",
    "declareWeight",
    "wfsActualWeight",
    "firstLegWeight",
  ])).length;

  const cards: SummaryCardItem[] = [
    {
      key: "total",
      title: "产品总数",
      value: total,
      hint: "当前筛选范围",
      icon: "品",
    },
    {
      key: "missingPurchasePrice",
      title: "缺采购价",
      value: missingPurchasePrice,
      hint: "采购价为空",
      icon: "价",
    },
    {
      key: "missingDimension",
      title: "缺尺寸",
      value: missingDimension,
      hint: "长宽高或尺寸为空",
      icon: "尺",
    },
    {
      key: "missingPurchaseLeadTime",
      title: "缺采购交期",
      value: missingPurchaseLeadTime,
      hint: "采购交期为空",
      icon: "期",
    },
    {
      key: "missingImage",
      title: "缺图片",
      value: missingImage,
      hint: "图片数量少于 2",
      icon: "图",
    },
    {
      key: "missingWeight",
      title: "缺重量",
      value: missingWeight,
      hint: "重量字段为空",
      icon: "重",
    },
  ];

  return (
    <section className="product-management__summary-cards" aria-label="产品管理统计">
      {cards.map((card) => (
        <article key={card.key} className="product-management__summary-card">
          <div className="product-management__summary-icon">{card.icon}</div>
          <div className="product-management__summary-content">
            <span className="product-management__summary-title">{card.title}</span>
            <strong className="product-management__summary-value">
              {numberFormatter.format(card.value)}
            </strong>
            <span className="product-management__summary-hint">{card.hint}</span>
          </div>
        </article>
      ))}
    </section>
  );
}
