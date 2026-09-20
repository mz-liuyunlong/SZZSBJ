export type ListingAnalysisPanel =
  | "overview"
  | "compare"
  | "price"
  | "adsAnalysis"
  | "profit"
  | "stock"
  | "risk"
  | "timeline";

export type ListingAnalysisPeriod = 7 | 14 | 30;

export interface ListingAnalysisSource {
  title?: string;
  productName?: string;
  itemName?: string;
  sku?: string;
  msku?: string;
  productId?: string;
  date?: string;
  platform?: string;
  status?: string;
  store?: string;
  listPrice?: number;
  salePrice?: number;
  rating?: number;
  reviewCount?: number;
  wfsAvailableInventory?: number;
}
