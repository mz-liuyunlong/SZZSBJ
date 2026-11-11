/** PR337_UNIFIED_MOCK_ROWS_V75
 * Local development acceptance data only. NEVER request or persist this data.
 * Replaces old per-table fake groups with Product[] records so all summaries use
 * the same source, product fields, filters and scoring functions. Not production.
 */
import dayjs from "dayjs";
import type { Product } from "./nativeData";

const categories = [
  "厨房用品", "收纳整理", "家居耗材", "办公收纳", "清洁工具",
  "浴室用品", "家居装饰", "园艺用品", "宠物用品", "运动配件",
  "旅行用品", "汽车用品", "餐具用品", "厨房工具", "衣物护理",
  "节庆用品", "储物用品", "桌面收纳", "包装耗材", "户外用品",
];
const developers = [
  "王宁", "李敏", "陈晨", "张敏", "赵磊", "周琳", "孙杰", "吴静", "刘凯", "林晓",
  "何佳", "郑宇", "朱婷", "马超", "韩雪", "许晨", "郭阳", "蒋雯", "谢楠", "邓博",
];
const productNames = [
  "硅胶厨房刮刀", "透明分格收纳盒", "超细纤维清洁布", "金属桌面置物架", "伸缩清洁除尘掸",
  "浴室防滑沥水架", "磁吸照片展示架", "折叠园艺工具袋", "宠物便携水碗", "运动水杯收纳架",
  "旅行分装收纳瓶", "车载座椅挂钩", "陶瓷餐具收纳架", "不锈钢压蒜器", "折叠衣物收纳箱",
  "节日装饰挂钩", "透明密封储物罐", "多功能桌面笔筒", "打包封箱辅助器", "露营便携挂架",
];

export function makeNewProductDevMockRows(original: Product[]): Product[] {
  const template = original[0];
  if (!template) return [];
  // 100 products: exactly 20 categories and 20 developers, 25+ pending market
  // assessments over 30 days; all use real Product field types and ID lookup.
  return Array.from({ length: 100 }, (_, i): Product => {
    const category = categories[i % categories.length];
    const developer = developers[(i * 7 + Math.floor(i / 20)) % developers.length];
    const pending = i % 4 === 0;
    const age = pending ? 31 + (i % 23) : 4 + (i * 11 % 49);
    const market = pending ? null : [3.1, 4.7, 5.9, 6.7, 7.5, 8.4, 9.2][i % 7];
    const speed = [2, 4, 6, 7.5, 8, 9, 10][(i * 3 + 2) % 7];
    const ad = [2, 4, 5.5, 7, 8, 9, 10][(i * 5 + 1) % 7];
    const profit = [2, 3, 5, 6, 7, 8.5, 9.5][(i * 2 + 3) % 7];
    const trust = [3, 5, 6, 7, 8, 9, 10][(i + Math.floor(i / 7)) % 7];
    const roi = i % 15 === 1 ? 0.45 : i % 9 === 2 ? 0.72 : 0.9 + (i % 13) * 0.095;
    const units = 2 + (i * 7 % 29);
    const quantity = 1 + (i * 3 % 18);
    const id = String(2001 + i);
    return {
      ...template,
      id: `NP-${id}`,
      sku: `YC${String(20001 + i)}`,
      item: String(20840000000 + i),
      name: `${productNames[i % productNames.length]}${["", " 大号", " 2件套", " 加厚款", " 升级款"][Math.floor(i / 20)]}`,
      category,
      owner: developer,
      developer,
      operator: developer,
      days: age,
      launch: dayjs().subtract(age, "day").format("YYYY-MM-DD"),
      arrival: dayjs().subtract(age + 7, "day").format("YYYY-MM-DD"),
      market,
      marketReason: pending ? "" : "竞品售价、评价数量和产品差异化的综合测评记录",
      scores: { speed, ad, profit, trust },
      overrides: undefined,
      penalties: i % 17 === 0 ? 1 : 0,
      penaltyFlags: [],
      roi,
      margin: 8 + i % 26,
      acos: 14 + i % 44,
      clicks: 18 + (i * 13) % 220,
      orders: quantity,
      qty7: quantity,
      sales30: units,
      spend: 18 + (i * 8) % 140,
      price: 12.99 + (i % 12),
      unitCost: 4.1 + (i % 8),
      inventory: 7 + i % 31,
      status: pending ? "待市场评分" : i % 6 === 1 ? "审核中" : i % 6 === 3 ? "已批准" : "待采购确认",
      risk: roi < 0.5 ? "ROI 偏低" : "无异常",
      suggested: null,
      requestQty: null,
      requestReason: "",
      tracking: "继续观察",
      actualQty: 0,
      sales60: units,
      sales90: units,
      margin60: 8 + i % 26,
      acos60: 14 + i % 44,
      sold30: units,
      sold60: units,
      sold90: units,
      reasonFailure: "",
    };
  });
}
