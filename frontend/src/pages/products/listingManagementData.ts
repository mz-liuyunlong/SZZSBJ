/** Listing-management No-API acceptance data; replace it when a real API is approved. */
export interface LifecyclePreviewDiagnostic {
  reasonCode: string;
  reasons: Array<{ code: string; title: string; detail: string; advice: string }>;
  evidence: Array<{ label: string; value: string }>;
  cutoffLa: string;
  ruleVersion: number;
}

// SZZSBJ_GRADE_LOCAL_PREVIEW_V1: only a non-published diagnostic, never a stored grade.
export interface ListingGradePreviewDiagnostic {
  reason: string;
  cutoffLa: string;
  candidate?: string;
  valid7?: number;
  valid14?: number;
  margin7?: string | null;
  margin14?: string | null;
  weightedMargin?: string | null;
  sourceVerified: boolean;
}

export interface ListingManagementRow {
  id: string;
  sourceAccountRef?: string;
  image: string;
  msku: string;
  productId: string;
  store: string;
  owner: string;
  sku: string;
  productName: string;
  title: string;
  productType: string;
  listPrice: number | null;
  salePrice: number | null;
  productStatus: string;
  lifecycle: string;
  /** True only for a local read-only preview; never persisted in the backend. */
  lifecyclePreview?: boolean;
  lifecyclePreviewReason?: string;
  lifecycleDiagnostic?: LifecyclePreviewDiagnostic;
  fulfillmentMethod: string;
  listedAt: string;
  category: string;
  wfsAvailableInventory: number;
  inboundInventory: number;
  sales90Days: number;
  adSpend30Days: number;
  disabledReason: string;
  listingStatus: string;
  buyBoxStatus: string;
  walmartSeller: string;
  resold: string;
  checkedAt: string;
  rating: number | null;
  reviewCount: number | null;
  hasStrikethrough?: boolean | null;
  strikethroughSource?: string;
  sellerNames?: string[];
  sellerOfferCount?: number | null;
  otherSellersPresent?: boolean | null;
  imageUrls?: string[];
  imageCount?: number | null;
  keyFeatures?: string[];
  reviewFetchStatus?: string;
  monitorSource?: string;
  brand: string;
  tags: string[];
  productTags?: Array<{ id: string | null; label: string; color: string | null }>;
  productTagMatchStatus?: string;
  gtin: string;
  productGrade: string;
  gradePreviewCandidate?: boolean;
  gradeDiagnostic?: ListingGradePreviewDiagnostic;
  archiveReason?: string | null;
  isArchived: boolean;
}

// LISTING_LAYOUT_20261104_V2: business-approved table order; hidden fields remain in API.
export const listingLifecycleOptions = [
  { label: "测品期", value: "测品期" },
  { label: "打品期", value: "打品期" },
  { label: "启动期", value: "启动期" },
  { label: "上升期", value: "上升期" },
  { label: "稳定期", value: "稳定期" },
  { label: "下滑期", value: "下滑期" },
  { label: "断货期", value: "断货期" },
  { label: "修复期", value: "修复期" },
] as const;

export const listingColumnFields = [
  { key: "image", title: "\u56fe\u7247" },
  { key: "productIdName", title: "\u5546\u54c1ID/\u54c1\u540d" },
  { key: "skuMsku", title: "SKU/MSKU" },
  { key: "storeOwner", title: "\u5e97\u94fa/\u8d1f\u8d23\u4eba" },
  { key: "title", title: "\u6807\u9898" },
  { key: "imageCount", title: "\u56fe\u7247\u6570\u91cf" },
  { key: "listPrice", title: "\u5212\u7ebf\u4ef7" },
  { key: "hasStrikethrough", title: "\u6709\u65e0\u5212\u7ebf\u4ef7" },
  { key: "salePrice", title: "\u5728\u552e\u4ef7" },
  { key: "category", title: "\u7c7b\u76ee" },
  { key: "wfsAvailableInventory", title: "WFS\u53ef\u552e\u5e93\u5b58" },
  { key: "inboundInventory", title: "\u5728\u9014\u5e93\u5b58" },
  { key: "listedAt", title: "\u4e0a\u67b6\u65f6\u95f4" },
  { key: "sales90Days", title: "\u8fd130\u5929\u9500\u91cf" },
  { key: "adSpend30Days", title: "\u8fd130\u5929\u5e7f\u544a\u8d39" },
  { key: "lifecycle", title: "\u751f\u547d\u5468\u671f" },
  { key: "productGrade", title: "listing\u7b49\u7ea7" },
  { key: "disabledReason", title: "\u505c\u7528\u539f\u56e0" },
  { key: "listingStatus", title: "Listing\u72b6\u6001" },
  { key: "buyBoxStatus", title: "\u8d2d\u7269\u8f66\u72b6\u6001" },
  { key: "brand", title: "\u54c1\u724c" },
  { key: "walmartSeller", title: "Walmart\u5356\u5bb6" },
  { key: "sellerOfferCount", title: "\u5356\u5bb6\u6570\u91cf" },
  { key: "sellerNames", title: "\u5356\u5bb6\u5217\u8868" },
  { key: "resold", title: "\u662f\u5426\u88ab\u8ddf\u5356" },
  { key: "checkedAt", title: "\u76d1\u63a7\u65e5\u671f" },
  { key: "rating", title: "\u8bc4\u5206" },
  { key: "reviewCount", title: "\u8bc4\u8bba\u6570" },
  { key: "keyFeatures", title: "\u4e94\u70b9\u63cf\u8ff0" },
  { key: "tags", title: "\u6807\u7b7e" },
  { key: "productTags", title: "产品标签" },
  { key: "fulfillmentMethod", title: "\u53d1\u8d27\u65b9\u5f0f" },
  { key: "gtin", title: "GTIN" },
  { key: "gptAnalysis", title: "GPT\u5206\u6790" },
  { key: "archiveReason", title: "\u5f52\u6863\u539f\u56e0" },
] as const;

export const fixedListingColumnKeys = ["image", "productIdName", "skuMsku"];

export const listingStores = ["美国一店", "美国二店", "加拿大店", "验收测试"];
export const listingOwners = ["林晓", "陈宁", "周琳", "赵明"];
export const listingProductTypes = ["常规产品", "季节产品", "组合产品"];
const categories = ["家居", "户外", "厨房", "收纳"];
const brands = ["NorthPeak", "HomeEase", "DailyNest"];
const tagPatterns = [["主推"], ["新品"], ["清货"], ["主推", "稳定"]];
const images = ["🎧", "⌚", "🔋", "☕", "🎒", "📱", "💡", "▤", "🧴", "🍳"];

export const listingManagementMockData: ListingManagementRow[] = Array.from(
  { length: 100 },
  (_, index) => {
    const number = index + 1;
    const serial = String(number).padStart(3, "0");
    const productStatus = index % 9 === 0 ? "停用" : "启用";
    return {
      id: `listing-${serial}`,
      image: images[index % images.length],
      msku: `LM-${serial}`,
      productId: `WMT-${124000000 + number}`,
      store: listingStores[index % listingStores.length],
      owner: listingOwners[index % listingOwners.length],
      sku: `SKU-${String(9000 + number)}`,
      productName: `Listing 验收产品 ${serial}`,
      title: `No-API Listing acceptance title ${serial}`,
      productType: listingProductTypes[index % listingProductTypes.length],
      listPrice: Number((19.99 + index * 0.7).toFixed(2)),
      salePrice: Number((16.99 + index * 0.65).toFixed(2)),
      productStatus,
      lifecycle: index % 4 === 0 ? "成长期" : "成熟期",
      fulfillmentMethod: index % 2 === 0 ? "WFS" : "Seller Fulfilled",
      listedAt: `2026-08-${String(index % 28 + 1).padStart(2, "0")}`,
      category: categories[index % categories.length],
      wfsAvailableInventory: 40 + index * 3,
      inboundInventory: index % 5 * 12,
      sales90Days: 180 + index * 7,
      adSpend30Days: Number((25 + index * 2.4).toFixed(2)),
      disabledReason: productStatus === "停用" ? "待复核" : "",
      listingStatus: index % 9 === 0 ? "离线" : "在线",
      buyBoxStatus: index % 6 === 0 ? "未拥有" : "拥有",
      walmartSeller: index % 3 === 0 ? "Walmart" : "第三方卖家",
      resold: index % 8 === 0 ? "是" : "否",
      checkedAt: `2026-09-09 ${String(8 + index % 10).padStart(2, "0")}:30`,
      rating: Number((3.8 + (index % 12) / 10).toFixed(1)),
      reviewCount: 15 + index * 9,
      brand: brands[index % brands.length],
      tags: tagPatterns[index % tagPatterns.length],
      gtin: `0085000${String(100000 + number)}`,
      productGrade: ["A级", "B级", "C级"][index % 3],
      isArchived: false,
    };
  },
);
