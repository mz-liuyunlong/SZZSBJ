import { productColumnFields, type ProductManagementRow } from "@/pages/products/productManagementTypes";

interface ProductBasicCompletenessFlags {
  purchasePrice: boolean;
  dimensions: boolean;
  purchaseLeadTime: boolean;
  images: boolean;
  weight: boolean;
}

const productBasicCompletenessColumnKey = productColumnFields.find((field) => (
  String(field.title).includes("资料完整度")
))?.key;

const emptyValues = new Set([
  "",
  "-",
  "--",
  "暂无数据",
  "无法计算",
  "null",
  "undefined",
]);

const isFilledText = (value: string) => !emptyValues.has(value.trim());

const extractPositiveNumber = (value: unknown) => {
  if (typeof value === "number") {
    return Number.isFinite(value) && value > 0;
  }

  if (typeof value !== "string") {
    return false;
  }

  const text = value.trim();

  if (!isFilledText(text)) {
    return false;
  }

  const matches = text.match(/-?\d+(?:\.\d+)?/g);

  if (!matches) {
    return true;
  }

  return matches.some((item) => Number(item) > 0);
};

const hasFilledValue = (value: unknown): boolean => {
  if (value === null || value === undefined) return false;

  if (Array.isArray(value)) {
    return value.some(hasFilledValue);
  }

  if (typeof value === "string") {
    return isFilledText(value);
  }

  if (typeof value === "number") {
    return Number.isFinite(value);
  }

  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "object") {
    return Object.values(value as Record<string, unknown>).some(hasFilledValue);
  }

  return true;
};

const hasPositiveField = (row: ProductManagementRow, keys: string[]) => {
  const record = row as unknown as Record<string, unknown>;
  return keys.some((key) => extractPositiveNumber(record[key]));
};

const hasAnyFilledField = (row: ProductManagementRow, keys: string[]) => {
  const record = row as unknown as Record<string, unknown>;
  return keys.some((key) => hasFilledValue(record[key]));
};

const getImageCount = (row: ProductManagementRow) => {
  const record = row as unknown as Record<string, unknown>;
  const images = new Set<string>();

  const collect = (value: unknown) => {
    if (!hasFilledValue(value)) return;

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
  collect(record.productImageUrl);

  return images.size;
};

const hasDimensions = (row: ProductManagementRow) => {
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

  if (dimensionTextKeys.some((key) => hasFilledValue(record[key]))) {
    return true;
  }

  const lengthKeys = ["length", "packageLength", "outerLength", "productLength"];
  const widthKeys = ["width", "packageWidth", "outerWidth", "productWidth"];
  const heightKeys = ["height", "packageHeight", "outerHeight", "productHeight"];

  return (
    lengthKeys.some((key) => extractPositiveNumber(record[key])) &&
    widthKeys.some((key) => extractPositiveNumber(record[key])) &&
    heightKeys.some((key) => extractPositiveNumber(record[key]))
  );
};

export const getProductBasicCompletenessFlags = (row: ProductManagementRow): ProductBasicCompletenessFlags => ({
  purchasePrice: hasPositiveField(row, [
    "purchasePrice",
    "productPurchasePrice",
    "procurementPrice",
    "purchaseCost",
    "costPrice",
    "basePurchasePrice",
    "productCost",
  ]),
  dimensions: hasDimensions(row),
  purchaseLeadTime: hasPositiveField(row, [
    "purchaseLeadTime",
    "purchaseLeadDays",
    "purchaseCycle",
    "purchaseDeliveryTime",
    "purchaseDeliveryDays",
    "procurementLeadTime",
    "leadTime",
  ]),
  images: getImageCount(row) >= 2,
  weight: hasPositiveField(row, [
    "weight",
    "packageWeight",
    "grossWeight",
    "netWeight",
    "shippingWeight",
    "productWeight",
    "packageActualWeight",
    "actualWeight",
    "declareWeight",
    "declaredWeight",
    "firstLegWeight",
    "firstLegActualWeight",
    "firstLegBillableWeight",
    "firstLegPhysicalWeight",
    "wfsActualWeight",
  ]) || hasAnyFilledField(row, [
    "packageWeightText",
    "grossWeightText",
    "weightText",
  ]),
});

export const calculateProductBasicCompleteness = (row: ProductManagementRow) => {
  const flags = getProductBasicCompletenessFlags(row);
  const values = Object.values(flags);
  const finishedCount = values.filter(Boolean).length;

  return Math.round((finishedCount / values.length) * 10000) / 100;
};

export const formatProductBasicCompleteness = (row: ProductManagementRow) => {
  const value = calculateProductBasicCompleteness(row);
  return Number.isInteger(value) ? `${value}%` : `${value.toFixed(2)}%`;
};

export const applyProductBasicCompleteness = (rows: ProductManagementRow[]) => (
  rows.map((row) => (
    productBasicCompletenessColumnKey
      ? ({
          ...row,
          [productBasicCompletenessColumnKey]: calculateProductBasicCompleteness(row),
        } as ProductManagementRow)
      : row
  ))
);
