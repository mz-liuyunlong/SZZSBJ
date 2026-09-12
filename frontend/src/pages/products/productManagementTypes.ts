export type ProductGrade = "A级" | "B级" | "C级";

export type ProductTag = "测品" | "清货" | "停售";

export interface ProductManagementRow {
  id: string;
  image: string;
  sku: string;
  productName: string;
  tags: ProductTag[];
  productGrade: ProductGrade;
  category: string;
  purchasePrice: number;
  firstLegFreight: number;
  wfsDeliveryFee: number;
  purchaseLeadTime: string;
  storageFee: number;
  wfsFee: string;
  suggestedPrice: string;
  minimumPrice: string;
  clearancePrice: string;
  materialCn: string;
  materialEn: string;
  usageCn: string;
  usageEn: string;
  customsNameCn: string;
  customsNameEn: string;
  packageSpec: string;
  cartonSpec: string;
  productSpec: string;
  grossWeightKg: number;
  netWeightKg: number;
  dataCompleteness: number;
  linkedPlatformSkuCount: number;
  updatedAt: string;
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
