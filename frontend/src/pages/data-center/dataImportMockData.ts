import type { DataImportRecord, DataImportTypeOption } from "@/pages/data-center/dataImportTypes";

export const dataImportTypes: DataImportTypeOption[] = [
  {
    id: "ad_fee",
    name: "沃尔玛广告费用",
    shortName: "每日广告花费",
    icon: "💵",
    fields: ["日期", "店铺", "Campaign ID", "广告花费", "币种"],
  },
  {
    id: "ad_bill",
    name: "沃尔玛广告账单",
    shortName: "平台账单核对",
    icon: "🧾",
    fields: ["账单月份", "店铺", "账单号", "账单金额", "状态"],
  },
  {
    id: "auto_ads",
    name: "沃尔玛自动广告",
    shortName: "自动广告表现",
    icon: "📢",
    fields: ["日期", "广告活动", "广告组", "搜索词", "花费"],
  },
  {
    id: "copy",
    name: "竞品文案信息",
    shortName: "标题五点描述",
    icon: "📝",
    fields: ["竞品链接", "标题", "五点", "描述", "类目"],
  },
  {
    id: "keywords",
    name: "卖家精灵关键词",
    shortName: "关键词数据",
    icon: "🔎",
    fields: ["关键词", "搜索量", "竞争度", "建议出价", "相关度"],
  },
  {
    id: "image",
    name: "竞品图片分析表",
    shortName: "图片卖点分析",
    icon: "🖼️",
    fields: ["图片链接", "图片类型", "场景", "卖点", "风格标签"],
  },
];

const fileNames = [
  "ad_fee_0913.xlsx",
  "ad_bill_aug.xlsx",
  "auto_ads_report.xlsx",
  "competitor_copy.xlsx",
  "seller_sprite_kw.csv",
  "image_analysis.xlsx",
  "ad_fee_0912.xlsx",
  "auto_ads_week.xlsx",
  "keyword_export_0911.csv",
  "copy_0909.xlsx",
];

const operators = ["陈宁", "林晓", "周琳", "赵明", "王倩", "刘洋"];

export const dataImportRecords: DataImportRecord[] = Array.from({ length: 100 }, (_, index) => {
  const type = dataImportTypes[index % dataImportTypes.length];
  const date = new Date(2026, 8, 13 - (index % 30));
  const status = index % 13 === 0 ? "失败" : index % 4 === 0 ? "部分失败" : "成功";
  const failedRows = status === "成功" ? 0 : status === "失败" ? 20 + index : 3 + (index % 9);
  const totalRows = status === "失败" ? 0 : 320 + index * 17;

  return {
    id: `import-record-${String(index + 1).padStart(3, "0")}`,
    uploadedAt: `${date.toISOString().slice(0, 10)} ${String(9 + (index % 10)).padStart(2, "0")}:${String((index * 7) % 60).padStart(2, "0")}`,
    typeName: type.name,
    fileName: fileNames[index % fileNames.length],
    status,
    totalRows,
    successRows: Math.max(totalRows - failedRows, 0),
    failedRows,
    operator: operators[index % operators.length],
  };
});
