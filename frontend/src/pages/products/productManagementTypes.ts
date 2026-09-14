export type ProductGrade = "A级" | "B级" | "C级";

export type ProductTag = string;

export interface ProductManagementRow {
  id: string;
  image: string | null;
  images: string[];
  sku: string | null;
  productName: string | null;
  tags: ProductTag[];
  productGrade: ProductGrade | "异常" | null;
  category: string | null;
  purchasePrice: string | null;
  firstLegFreight: string | null;
  wfsDeliveryFee: string | null;
  purchaseLeadTime: string | null;
  storageFee: string | null;
  wfsFee: string | null;
  suggestedPrice: string | null;
  minimumPrice: string | null;
  clearancePrice: string | null;
  materialCn: string | null;
  materialEn: string | null;
  usageCn: string | null;
  usageEn: string | null;
  customsNameCn: string | null;
  customsNameEn: string | null;
  packageSpec: string | null;
  cartonSpec: string | null;
  productSpec: string | null;
  grossWeightKg: string | null;
  netWeightKg: string | null;
  dataCompleteness: number | null;
  linkedPlatformSkuCount: number;
  updatedAt: string | null;
}

export interface ProductManagementFilters {
  productGrade?: ProductGrade;
  tag?: ProductTag;
  searchType: "sku" | "productName" | "category";
  keyword: string;
  batchValues?: string[];
}

export const productColumnFields = [
  { key: "image", title: "图片" },
  { key: "sku", title: "SKU" },
  { key: "productName", title: "产品名称" },
  { key: "tags", title: "标签" },
  { key: "productGrade", title: "产品等级" },
  { key: "wfsFee", title: "WFS费用" },
  { key: "suggestedPrice", title: "建议售价" },
  { key: "minimumPrice", title: "最低售价" },
  { key: "clearancePrice", title: "清仓售价" },
  { key: "category", title: "类目" },
  { key: "purchasePrice", title: "产品采购价" },
  { key: "firstLegFreight", title: "头程运费" },
  { key: "wfsDeliveryFee", title: "WFS配送费" },
  { key: "purchaseLeadTime", title: "采购交期" },
  { key: "storageFee", title: "仓储费" },
  { key: "linkedPlatformSkuCount", title: "平台SKU数" },
  { key: "dataCompleteness", title: "资料完整度" },
  { key: "updatedAt", title: "更新时间" },
] as const;

export const fixedProductColumnKeys = ["image", "sku"];
