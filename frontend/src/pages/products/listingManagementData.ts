/** Static acceptance data for the Listing Management No-API page shell. */
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
  { key: "listingStatus", title: "listing状态" },
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

const stores = ["美国一店", "美国二店", "加拿大店", "验收测试"];
const owners = ["林晓", "陈宁", "周琳", "赵明"];
const productTypes = ["常规产品", "季节产品", "组合产品"];
const categories = ["家居", "户外", "厨房", "收纳"];
const brands = ["NorthPeak", "HomeEase", "DailyNest"];
const tagPatterns = [["主推"], ["新品"], ["清货"], ["主推", "稳定"]];

export const listingManagementMockData: ListingManagementRow[] = Array.from(
  { length: 50 },
  (_, index) => {
    const number = index + 1;
    const serial = String(number).padStart(3, "0");
    return {
      id: `listing-${serial}`,
      image: "",
      msku: `LM-${serial}`,
      productId: `WMT-${124000000 + number}`,
      store: stores[index % stores.length],
      owner: owners[index % owners.length],
      sku: `SKU-${String(9000 + number)}`,
      productName: `Listing 验收产品 ${serial}`,
      title: `No-API Listing acceptance title ${serial}`,
      productType: productTypes[index % productTypes.length],
      listPrice: 19.99 + index,
      salePrice: 16.99 + index,
      productStatus: index % 9 === 0 ? "停用" : "启用",
      lifecycle: index % 4 === 0 ? "成长期" : "成熟期",
      listedAt: `2026-08-${String(index % 28 + 1).padStart(2, "0")}`,
      category: categories[index % categories.length],
      wfsAvailableInventory: 40 + index * 3,
      inboundInventory: index % 5 * 12,
      sales90Days: 180 + index * 7,
      adSpend30Days: 25 + index * 2.4,
      disabledReason: index % 9 === 0 ? "待接入" : "",
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

export const listingStores = stores;
export const listingOwners = owners;
export const listingProductTypes = productTypes;
