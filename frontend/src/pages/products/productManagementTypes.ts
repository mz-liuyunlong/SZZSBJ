export type ProductGrade = "A级" | "B级" | "C级";

export type ProductTag = string;

export type ProductManagementIssueCode =
  | "missing_purchase_cost"
  | "missing_purchase_delivery"
  | "missing_package_dimensions"
  | "missing_image"
  | "missing_gross_weight";

export interface ProductPersonOption {
  uid: string;
  name: string;
}

export interface ProductSourceTagOption {
  value: string;
  label: string;
  color: string | null;
}

export type ProductCalculationStatus =
  | "ok"
  | "pricing_unavailable"
  | "storage_unavailable"
  | "invalid_denominator";

export interface ProductPricingBreakdown {
  productGrossWeightG: string | null;
  grossWeightKg: string | null;
  packageLengthCm: string | null;
  packageWidthCm: string | null;
  packageHeightCm: string | null;
  firstLegVolumeWeightKg: string | null;
  firstLegChargeableWeightKg: string | null;
  firstLegCostPerKgCny: string | null;
  wfsActualWeightLb: string | null;
  wfsDimensionalWeightLb: string | null;
  wfsChargeableWeightLb: string | null;
  wfsWeightPaddingLb: string | null;
  wfsBaseFeeUsd: string | null;
  packageVolumeCuft: string | null;
  dailyStorageFeeUsd: string | null;
  fixedCostUsd: string | null;
  usdCnyRate: string | null;
  commissionRate: string | null;
  afterSalesRate: string | null;
  adCostRate: string | null;
  suggestedMarginRate: string | null;
  minimumMarginRate: string | null;
  detailMessages: string[];
  formulaVersion: string | null;
  wfsFormulaVersion: string | null;
}

export interface ProductManagementRow {
  id: string;
  image: string | null;
  previewImage?: string | null;
  sourceImage?: string | null;
  images: string[];
  imageCount: number;
  sku: string | null;
  productName: string | null;
  tags: ProductTag[];
  sourceTags: ProductTag[];
  sourceTagColors?: Record<string, string | null>;
  ownerUid: string | null;
  ownerName: string | null;
  developerUid: string | null;
  developerName: string | null;
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
  calculationStatus: ProductCalculationStatus | null;
  rootMissingCodes: string[];
  pricingAvailable: boolean;
  billingRootComplete: boolean;
  wfsCalculationStatus: string | null;
  wfsCalculationReason: string | null;
  storageCalculationStatus: string | null;
  firstLegCalculationStatus: string | null;
  formulaVersion: string | null;
  pricingBreakdown: ProductPricingBreakdown | null;
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

export interface ProductManagementSummary {
  total: number;
  syncedDetailCount: number;
  dataCompletenessRate: number;
  withImageCount: number;
  withSourceTagCount: number;
  incompleteCount: number;
  missingPurchaseCostCount: number;
  missingPurchaseDeliveryCount: number;
  missingGrossWeightCount: number;
  missingPackageDimensionsCount: number;
  missingImageCount: number;
  missingDimensionImageCount: number;
  invalidPricingRuleCount: number;
  pricingOkCount: number;
}

export interface ProductManagementFilters {
  productGrade?: ProductGrade;
  ownerUid?: string;
  developerUid?: string;
  tag?: string;
  issueCode?: ProductManagementIssueCode;
  searchType: "sku";
  keyword: string;
  batchValues?: string[];
}

export const productColumnFields = [
  { key: "image", title: "图片" },
  { key: "sku", title: "SKU" },
  { key: "productName", title: "产品名称" },
  { key: "ownerName", title: "负责人" },
  { key: "developerName", title: "开发人" },
  { key: "category", title: "类目" },
  { key: "purchasePrice", title: "产品采购价" },
  { key: "firstLegFreight", title: "头程运费" },
  { key: "purchaseLeadTime", title: "采购交期" },
  { key: "sourceTags", title: "标签" },
  { key: "wfsFee", title: "WFS费用" },
  { key: "clearancePrice", title: "清仓售价" },
  { key: "storageFee", title: "每日仓储费" },
] as const;

export const fixedProductColumnKeys = ["image", "sku"];
