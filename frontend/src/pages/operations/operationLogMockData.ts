import {
  OPERATION_LOG_REFERENCE_DATE,
  type OperationLogRow,
  type OperationLogSystemRecord,
  type OperationLogWorkType,
} from "@/pages/operations/operationLogTypes";

const productNames = [
  "折叠硅胶沥水篮",
  "抽屉分隔收纳盒",
  "透明文件收纳袋",
  "烘焙纸圆形垫片",
  "厨房清洁刷套装",
  "桌面理线夹",
  "一次性打包袋",
  "冰箱收纳盒",
  "浴室挂钩套装",
  "食品密封夹",
];

export const operationLogOwners = ["陈宁", "林晓", "周琳", "赵明", "王倩", "刘洋"];
export const operationLogStores = ["美国一店", "美国二店", "美国三店", "加拿大店"];
export const operationLogWorkTypeValues: OperationLogWorkType[] = [
  "广告调整",
  "Listing优化",
  "销售价调整",
  "无需调整",
  "系统日志核对",
];

const pad = (value: number, width = 8) => String(value).padStart(width, "0");

const dateForIndex = (index: number) => {
  const day = 13 - (index % 10);
  return `2026-09-${pad(day, 2)}`;
};

export const operationLogRows: OperationLogRow[] = Array.from({ length: 100 }, (_, index) => {
  const serial = index + 1;
  const systemLogCount = index % 7 === 0 ? 0 : (index % 4) + 1;
  const workType = operationLogWorkTypeValues[index % operationLogWorkTypeValues.length];

  return {
    id: `operation-log-${serial}`,
    date: dateForIndex(index),
    productId: `WMT-${pad(80000001 + index * 733)}`,
    sku: `ZS-${["KT", "ST", "OF", "BK", "HM"][index % 5]}-${pad(serial, 3)}`,
    productName: productNames[index % productNames.length],
    store: operationLogStores[index % operationLogStores.length],
    owner: operationLogOwners[index % operationLogOwners.length],
    workType,
    conversionRate: Number((2.1 + (index % 30) / 10).toFixed(1)),
    adRatio: systemLogCount ? Number((10 + (index % 25)).toFixed(1)) : undefined,
    salePrice: Number((6.99 + (index % 20) * 0.7).toFixed(2)),
    keywordEntryStatus: index % 9 === 0 ? "missing" : "ok",
    adEntryStatus: index % 11 === 0 ? "missing" : "ok",
    systemLogCount,
    manualLog: index % 8 === 0 ? "" : `已处理${workType}，继续观察数据变化。`,
    status: index % 6 === 0 ? "待提交" : index % 5 === 0 ? "缺记录" : index % 4 === 0 ? "已保存" : "草稿",
  };
});

export const operationSystemRecords: OperationLogSystemRecord[] = operationLogRows.flatMap((row, rowIndex) => (
  Array.from({ length: row.systemLogCount }, (_, logIndex) => ({
    id: `system-log-${row.id}-${logIndex}`,
    time: `${String(9 + ((rowIndex + logIndex) % 8)).padStart(2, "0")}:${String((rowIndex * 7 + logIndex * 11) % 60).padStart(2, "0")}`,
    productId: row.productId,
    owner: row.owner,
    type: ["广告出价", "预算调整", "否定关键词", "关键词新增"][logIndex % 4],
    object: ["Exact Campaign", "Auto Campaign", "高花费无单词", "核心关键词"][logIndex % 4],
    before: logIndex % 2 ? "$0.42" : "启用",
    after: logIndex % 2 ? "$0.48" : "否定精准",
    source: logIndex % 3 ? "领星" : "Walmart后台",
    detail: "系统抓取到广告调整记录，已按商品ID自动匹配。",
  }))
));

export const operationLogDefaultDate = OPERATION_LOG_REFERENCE_DATE;
