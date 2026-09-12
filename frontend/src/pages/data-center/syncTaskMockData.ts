/** No-API acceptance data for Sync Task Management; replace it when real sync-task APIs are approved. */
import type {
  SyncScheduleItem,
  SyncTaskLog,
  SyncTaskModule,
  SyncTaskRow,
  SyncTaskStatus,
  SyncTaskTriggerType,
} from "@/pages/data-center/syncTaskTypes";

export const syncTaskModules: SyncTaskModule[] = ["商品", "订单", "广告", "仓库", "财务", "售后"];

export const syncTaskStatuses: SyncTaskStatus[] = ["成功", "失败", "运行中", "部分成功", "超时", "已停用"];

const baseNotificationScenes = ["失败", "部分成功", "超时"];
const baseNotificationChannels = ["站内信", "飞书"];
const generatedStatuses: SyncTaskStatus[] = ["成功", "失败", "运行中", "部分成功", "超时", "已停用"];
const generatedModules: SyncTaskModule[] = ["商品", "订单", "广告", "仓库", "财务", "售后"];
const generatedTaskNames = [
  "WFS费用同步",
  "Listing质量扫描",
  "订单利润快照同步",
  "广告关键词排名同步",
  "Review看板同步",
  "入库差异同步",
  "退货管理同步",
  "单品现金利润同步",
  "库存库龄同步",
  "结算对账同步",
  "商品认领同步",
  "新品分析同步",
  "索赔赔付同步",
  "广告账单同步",
  "运营日志草稿同步",
  "销售趋势同步",
  "补货建议同步",
  "账号健康同步",
  "产品表现同步",
  "Walmart监控同步",
  "客户消息状态同步",
  "库存预警同步",
  "广告搜索词同步",
  "退货退款同步",
  "平台费用同步",
];

const createBaseTask = (
  task: Omit<SyncTaskRow, "timeoutSeconds" | "maxFailureTimes" | "duplicatePolicy" | "retryEnabled" | "retryTimes" | "retryInterval" | "notificationScenes" | "notificationChannels" | "notificationTargets">,
): SyncTaskRow => ({
  ...task,
  timeoutSeconds: task.cycle === "周任务" ? 1_800 : 600,
  maxFailureTimes: 3,
  duplicatePolicy: task.lastStatus === "运行中" ? "排队等待" : "忽略本次触发",
  retryEnabled: true,
  retryTimes: 3,
  retryInterval: task.lastStatus === "超时" ? "30 分钟" : "10 分钟",
  notificationScenes: baseNotificationScenes,
  notificationChannels: baseNotificationChannels,
  notificationTargets: `${task.module}负责人、技术支持`,
});

const primarySyncTaskRows: SyncTaskRow[] = [
  createBaseTask({
    id: "sync-amazon-orders",
    taskName: "Amazon订单同步",
    interfaceName: "Amazon Orders API",
    module: "订单",
    autoSync: true,
    frequency: "每15分钟",
    nextRunAt: "2026-09-13 00:00",
    lastStatus: "成功",
    lastRunAt: "2026-09-12 23:45",
    todaySuccess: 286,
    todayFailed: 0,
    description: "同步 Amazon 店铺订单数据，包含订单、买家、物流、支付等信息。",
    cycle: "日任务",
    dailyRunCount: 96,
    runTimes: ["00:00", "00:15", "00:30"],
    weekDays: [],
  }),
  createBaseTask({
    id: "sync-walmart-products",
    taskName: "Walmart商品同步",
    interfaceName: "Walmart Items API",
    module: "商品",
    autoSync: true,
    frequency: "每1小时",
    nextRunAt: "2026-09-13 00:00",
    lastStatus: "运行中",
    lastRunAt: "2026-09-12 23:28",
    todaySuccess: 128,
    todayFailed: 2,
    description: "同步 Walmart 商品、Listing、价格与库存基础状态。",
    cycle: "日任务",
    dailyRunCount: 24,
    runTimes: ["00:00", "01:00", "02:00"],
    weekDays: [],
  }),
  createBaseTask({
    id: "sync-temu-products",
    taskName: "Temu商品同步",
    interfaceName: "Temu Product API",
    module: "商品",
    autoSync: true,
    frequency: "每1小时",
    nextRunAt: "2026-09-13 00:00",
    lastStatus: "失败",
    lastRunAt: "2026-09-12 23:00",
    todaySuccess: 12,
    todayFailed: 8,
    description: "同步 Temu 商品信息、价格与在售状态。",
    cycle: "日任务",
    dailyRunCount: 24,
    runTimes: ["00:00", "01:00", "02:00"],
    weekDays: [],
  }),
  createBaseTask({
    id: "sync-lingxing-ads",
    taskName: "领星广告报表同步",
    interfaceName: "Lingxing Ads Report API",
    module: "广告",
    autoSync: true,
    frequency: "每2小时",
    nextRunAt: "2026-09-13 00:00",
    lastStatus: "部分成功",
    lastRunAt: "2026-09-12 22:12",
    todaySuccess: 58,
    todayFailed: 4,
    description: "同步领星广告活动、关键词、搜索词、花费与转化表现。",
    cycle: "日任务",
    dailyRunCount: 12,
    runTimes: ["00:00", "02:00", "04:00"],
    weekDays: [],
  }),
  createBaseTask({
    id: "sync-price-monitor",
    taskName: "价格监控同步",
    interfaceName: "Marketplace Price Monitor API",
    module: "商品",
    autoSync: true,
    frequency: "每6小时",
    nextRunAt: "2026-09-13 00:00",
    lastStatus: "超时",
    lastRunAt: "2026-09-12 18:02",
    todaySuccess: 0,
    todayFailed: 3,
    description: "同步平台价格监控数据，用于识别异常调价、跟卖和价格波动。",
    cycle: "日任务",
    dailyRunCount: 4,
    runTimes: ["00:00", "06:00", "12:00", "18:00"],
    weekDays: [],
  }),
  createBaseTask({
    id: "sync-inventory-snapshot",
    taskName: "库存快照同步",
    interfaceName: "Inventory Snapshot API",
    module: "仓库",
    autoSync: true,
    frequency: "每30分钟",
    nextRunAt: "2026-09-13 00:00",
    lastStatus: "成功",
    lastRunAt: "2026-09-12 23:30",
    todaySuccess: 320,
    todayFailed: 0,
    description: "同步 WFS、海外仓、平台库存快照，供库存预警和补货建议使用。",
    cycle: "日任务",
    dailyRunCount: 48,
    runTimes: ["00:00", "00:30", "01:00"],
    weekDays: [],
  }),
  createBaseTask({
    id: "sync-finance-settlement",
    taskName: "财务结算数据同步",
    interfaceName: "Finance Settlement API",
    module: "财务",
    autoSync: false,
    frequency: "每周五 04:00",
    lastStatus: "已停用",
    lastRunAt: "2026-09-11 04:01",
    todaySuccess: 0,
    todayFailed: 0,
    description: "同步平台结算、费用、返还明细，用于财务对账和利润核算。",
    cycle: "周任务",
    dailyRunCount: 1,
    runTimes: ["04:00"],
    weekDays: ["周五"],
  }),
  createBaseTask({
    id: "sync-customer-message",
    taskName: "客户消息同步",
    interfaceName: "Customer Message API",
    module: "售后",
    autoSync: true,
    frequency: "每10分钟",
    nextRunAt: "2026-09-12 23:50",
    lastStatus: "成功",
    lastRunAt: "2026-09-12 23:40",
    todaySuccess: 89,
    todayFailed: 0,
    description: "同步平台客户消息、Case 与客服待处理数据。",
    cycle: "日任务",
    dailyRunCount: 144,
    runTimes: ["00:00", "00:10", "00:20"],
    weekDays: [],
  }),
];

const generatedSyncTaskRows: SyncTaskRow[] = Array.from({ length: 100 }, (_, index) => {
  const number = index + 1;
  const serial = String(number).padStart(3, "0");
  const taskName = generatedTaskNames[index % generatedTaskNames.length];
  const module = generatedModules[index % generatedModules.length];
  const lastStatus = generatedStatuses[index % generatedStatuses.length];
  const isWeeklyTask = index % 5 === 0;
  const autoSync = lastStatus !== "已停用";
  const hour = String((index * 2) % 24).padStart(2, "0");
  const minute = String(index % 2 === 0 ? 0 : 30).padStart(2, "0");

  return createBaseTask({
    id: `sync-generated-${serial}`,
    taskName: `${taskName} ${serial}`,
    interfaceName: `${taskName.replace("同步", "")} API`,
    module,
    autoSync,
    frequency: isWeeklyTask
      ? `每周${["一", "三", "五"][index % 3]} ${hour}:${minute}`
      : index % 4 === 0
        ? "每30分钟"
        : index % 3 === 0
          ? "每2小时"
          : `每天 ${hour}:${minute}`,
    nextRunAt: autoSync ? `2026-09-13 ${hour}:${minute}` : undefined,
    lastStatus,
    lastRunAt: `2026-09-12 ${String(8 + index % 14).padStart(2, "0")}:${minute}`,
    todaySuccess: lastStatus === "已停用" ? 0 : 20 + index * 3,
    todayFailed: lastStatus === "成功" || lastStatus === "已停用" ? 0 : index % 7 + 1,
    description: `${taskName}的 No-API 验收数据，后续真实接口接入后替换。`,
    cycle: isWeeklyTask ? "周任务" : "日任务",
    dailyRunCount: isWeeklyTask ? 1 : 6,
    runTimes: isWeeklyTask ? [`${hour}:${minute}`] : ["02:00", "10:00", "18:00"],
    weekDays: isWeeklyTask ? ["周一", "周五"] : [],
  });
});

export const syncTaskRows: SyncTaskRow[] = [
  ...primarySyncTaskRows,
  ...generatedSyncTaskRows,
];

const triggerTypes: SyncTaskTriggerType[] = ["自动", "手动", "重试"];

const createLogsForTask = (task: SyncTaskRow, taskIndex: number): SyncTaskLog[] => Array.from({ length: 3 }, (_, logIndex) => {
  const status = logIndex === 0 ? task.lastStatus : logIndex === 1 ? "成功" : generatedStatuses[(taskIndex + logIndex) % generatedStatuses.length];
  const total = task.todaySuccess + task.todayFailed + logIndex * 4;
  const failed = status === "成功" ? 0 : Math.max(1, Math.min(task.todayFailed + logIndex, 12));
  const success = Math.max(0, total - failed);

  return {
    id: `log-${task.id}-${logIndex + 1}`,
    taskId: task.id,
    runAt: `2026-09-12 ${String(23 - logIndex).padStart(2, "0")}:${String((taskIndex + logIndex * 7) % 60).padStart(2, "0")}`,
    triggerType: triggerTypes[(taskIndex + logIndex) % triggerTypes.length],
    status,
    duration: `${1 + (taskIndex + logIndex) % 4}分${String(8 + taskIndex % 50).padStart(2, "0")}秒`,
    total,
    success,
    failed,
    requestId: `req_${String(taskIndex + 1).padStart(3, "0")}_${logIndex + 1}`,
    errorSummary: status === "成功" || status === "运行中"
      ? undefined
      : `${task.taskName}返回部分异常结果，请按 request_id 检索后端日志。`,
  };
});

export const syncTaskLogs: SyncTaskLog[] = syncTaskRows.flatMap((task, index) => createLogsForTask(task, index));

export const dayScheduleItems: SyncScheduleItem[] = syncTaskRows
  .filter((task) => task.cycle === "日任务" && task.autoSync)
  .slice(0, 18)
  .map((task, index) => ({
    id: `schedule-day-${task.id}`,
    time: task.runTimes[index % task.runTimes.length] ?? "00:00",
    taskName: task.taskName,
    module: task.module,
    frequency: task.frequency,
    status: task.lastStatus,
  }));

export const weekScheduleItems: SyncScheduleItem[] = syncTaskRows
  .filter((task) => task.cycle === "周任务")
  .slice(0, 21)
  .map((task, index) => ({
    id: `schedule-week-${task.id}`,
    time: task.runTimes[0] ?? "04:00",
    weekDay: task.weekDays[0] ?? (index % 2 === 0 ? "周一" : "周五"),
    taskName: task.taskName,
    module: task.module,
    frequency: task.frequency,
    status: task.lastStatus,
  }));
