/** Product-management No-API acceptance data; replace it when a real API is approved. */
import type {
  ProductGrade,
  ProductManagementRow,
  ProductTag,
} from "@/pages/products/productManagementTypes";

export const productGrades: ProductGrade[] = ["A级", "B级", "C级"];
export const productTags: ProductTag[] = ["测品", "清货", "停售"];

const images = ["🎧", "⌚", "🔋", "☕", "🎒", "📱", "💡", "▤", "🧴", "🍳", "🧺", "🧽"];
const productNames = [
  "无线蓝牙耳机 Air Pro",
  "智能手表 Watch 8",
  "便携充电宝 20000mAh",
  "咖啡保温杯 500ml",
  "户外折叠背包 30L",
  "手机支架 磁吸款",
  "LED台灯 护眼款",
  "桌面收纳盒 三层",
  "厨房密封罐套装",
  "硅胶烘焙垫",
  "衣柜收纳篮",
  "清洁海绵组合",
];
const categories = ["耳机", "智能手表", "充电设备", "水杯", "户外包", "车载支架", "灯具照明", "收纳用品", "厨房用品", "烘焙工具"];
const materials = [
  ["ABS塑料", "ABS Plastic"],
  ["不锈钢", "Stainless Steel"],
  ["硅胶", "Silicone"],
  ["聚酯纤维", "Polyester"],
  ["玻璃", "Glass"],
];

const tagPatterns: ProductTag[][] = [
  ["测品"],
  ["清货"],
  ["停售"],
  ["测品", "清货"],
  [],
];

const priceText = (value: number) => `$${value.toFixed(2)}`;

export const productManagementMockData: ProductManagementRow[] = Array.from({ length: 128 }, (_, index) => {
  const number = index + 1;
  const serial = String(number).padStart(3, "0");
  const grade = productGrades[index % productGrades.length];
  const tags = tagPatterns[index % tagPatterns.length];
  const purchasePrice = 4.5 + (index % 18) * 1.35;
  const firstLegFreight = 1.2 + (index % 9) * 0.32;
  const wfsDeliveryFee = 0.6 + (index % 7) * 0.28;
  const baseSale = purchasePrice + firstLegFreight + wfsDeliveryFee + 8 + (index % 8);
  const material = materials[index % materials.length];

  return {
    id: `product-${serial}`,
    image: images[index % images.length],
    sku: `UI-SAMPLE-${serial}`,
    productName: `${productNames[index % productNames.length]} ${serial}`,
    tags,
    productGrade: grade,
    category: categories[index % categories.length],
    purchasePrice,
    firstLegFreight,
    wfsDeliveryFee,
    purchaseLeadTime: `${8 + index % 18}天`,
    storageFee: 0.25 + (index % 8) * 0.08,
    wfsFee: index % 11 === 0 ? "待接入" : priceText(wfsDeliveryFee + 2.15),
    suggestedPrice: index % 7 === 0 ? "待接入" : priceText(baseSale),
    minimumPrice: index % 9 === 0 ? "待接入" : priceText(baseSale * 0.86),
    clearancePrice: index % 5 === 0 ? "待接入" : priceText(baseSale * 0.72),
    materialCn: material[0],
    materialEn: material[1],
    usageCn: "家居日用",
    usageEn: "Home daily use",
    customsNameCn: categories[index % categories.length],
    customsNameEn: `Customs ${categories[index % categories.length]}`,
    packageSpec: `${12 + index % 9}x${8 + index % 6}x${4 + index % 5}cm`,
    cartonSpec: `${42 + index % 8}x${36 + index % 7}x${28 + index % 6}cm`,
    productSpec: `${10 + index % 8}x${6 + index % 7}cm`,
    grossWeightKg: Number((0.18 + (index % 12) * 0.07).toFixed(2)),
    netWeightKg: Number((0.12 + (index % 10) * 0.06).toFixed(2)),
    dataCompleteness: 86 + (index % 14),
    linkedPlatformSkuCount: index % 6,
    updatedAt: `2026-09-${String(1 + index % 12).padStart(2, "0")} ${String(8 + index % 10).padStart(2, "0")}:30`,
  };
});
