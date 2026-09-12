/** Listing-management No-API acceptance data; replace it when a real API is approved. */
export interface ListingManagementRow {
  id: string;
  image: string;
  msku: string;
  productId: string;
  store: string;
  owner: string;
  sku: string;
  productName: string;
  title: string;
  productType: string;
  listPrice: number;
  salePrice: number;
  productStatus: string;
  lifecycle: string;
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
  rating: number;
  reviewCount: number;
  brand: string;
  tags: string[];
  gtin: string;
  productGrade: string;
}

export const listingColumnFields = [
  { key: "image", title: "图片" },
  { key: "msku", title: "MSKU" },
  { key: "productId", title: "商品ID" },
  { key: "store", title: "店铺" },
  { key: "owner", title: "负责人" },
  { key: "sku", title: "SKU" },
  { key: "productName", title: "品名" },
  { key: "title", title: "标题" },
  { key: "productType", title: "产品类型" },
  { key: "listPrice", title: "划线价" },
  { key: "salePrice", title: "在售价" },
  { key: "productStatus", title: "产品状态" },
  { key: "lifecycle", title: "生命周期" },
  { key: "listedAt", title: "上架时间" },
  { key: "category", title: "类目" },
  { key: "wfsAvailableInventory", title: "WFS可售库存" },
  { key: "inboundInventory", title: "在途库存" },
  { key: "sales90Days", title: "近90天销量" },
  { key: "adSpend30Days", title: "近30天广告费" },
  { key: "disabledReason", title: "停用原因" },
  { key: "listingStatus", title: "Listing状态" },
  { key: "buyBoxStatus", title: "购物车状态" },
  { key: "walmartSeller", title: "Walmart卖家" },
  { key: "resold", title: "是否被跟卖" },
  { key: "checkedAt", title: "检查时间" },
  { key: "rating", title: "评分" },
  { key: "reviewCount", title: "评论数" },
  { key: "brand", title: "品牌" },
  { key: "tags", title: "标签" },
  { key: "gtin", title: "GTIN" },
  { key: "productGrade", title: "产品等级" },
] as const;

export const fixedListingColumnKeys = ["image", "msku", "productId"];

export const listingStores = ["美国一店", "美国二店", "加拿大店", "验收测试"];
export const listingOwners = ["林晓", "陈宁", "周琳", "赵明"];
export const listingProductTypes = ["常规产品", "季节产品", "组合产品"];
const categories = ["家居", "户外", "厨房", "收纳"];
const brands = ["NorthPeak", "HomeEase", "DailyNest"];
const tagPatterns = [["主推"], ["新品"], ["清货"], ["主推", "稳定"]];
const images = ["🎧", "⌚", "🔋", "☕", "🎒", "📱", "💡", "▤", "🧴", "🍳"];

export const listingManagementMockData: ListingManagementRow[] = Array.from(
  { length: 128 },
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
    };
  },
);
