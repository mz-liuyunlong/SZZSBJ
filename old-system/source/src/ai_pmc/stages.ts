/**
 * stages.ts - AI 智能 PMC 阶段枚举常量（P1-4）
 *
 * checkStatus 产出的 stage、通知日志 task_stage、防重复判断三者
 * 必须统一使用本文件的枚举值，禁止自由文本。
 */

/** 任务阶段（用于台账 F 列、通知日志 task_stage、防重复键） */
export enum Stage {
  /** 审批通过未下单 (R001) */
  APPROVE_PENDING = "APPROVE_PENDING",
  /** 已下单未到货，含部分到货 (R002) */
  ARRIVAL_PENDING = "ARRIVAL_PENDING",
  /** 已到仓待发货 (R003) */
  ARRIVED_PENDING_SHIP = "ARRIVED_PENDING_SHIP",
  /** 到仓逾期未发货 (R004) */
  OVERDUE_SHIP = "OVERDUE_SHIP",
  /** 审批未下单升级 (R001 超 14 天) */
  ESCALATE_APPROVE = "ESCALATE_APPROVE",
  /** 未到货升级 (R002 超 21 天) */
  ESCALATE_ARRIVAL = "ESCALATE_ARRIVAL",
  /** 未发货升级 (R004 超 10 天) */
  ESCALATE_SHIP = "ESCALATE_SHIP",
  /** 已完成（终态，不再提醒） */
  DONE = "DONE",
}

/** 阶段 → 中文名称（用于消息展示与台账人类可读列） */
export const STAGE_LABEL: Record<Stage, string> = {
  [Stage.APPROVE_PENDING]: "采购下单",
  [Stage.ARRIVAL_PENDING]: "到货跟进",
  [Stage.ARRIVED_PENDING_SHIP]: "到仓发货",
  [Stage.OVERDUE_SHIP]: "到仓逾期",
  [Stage.ESCALATE_APPROVE]: "审批升级",
  [Stage.ESCALATE_ARRIVAL]: "到货升级",
  [Stage.ESCALATE_SHIP]: "发货升级",
  [Stage.DONE]: "已完成",
};

/** 阶段 → 台账「任务状态」(G 列) 文案 */
export const STAGE_TASK_STATUS: Record<Stage, string> = {
  [Stage.APPROVE_PENDING]: "待下单",
  [Stage.ARRIVAL_PENDING]: "已下单待到货",
  [Stage.ARRIVED_PENDING_SHIP]: "已到仓待发货",
  [Stage.OVERDUE_SHIP]: "逾期",
  [Stage.ESCALATE_APPROVE]: "逾期",
  [Stage.ESCALATE_ARRIVAL]: "逾期",
  [Stage.ESCALATE_SHIP]: "逾期",
  [Stage.DONE]: "已完成",
};

/** 升级阶段集合（单独防重复，避免重复 @ 总负责人） */
export const ESCALATE_STAGES: ReadonlySet<Stage> = new Set([
  Stage.ESCALATE_APPROVE,
  Stage.ESCALATE_ARRIVAL,
  Stage.ESCALATE_SHIP,
]);

export function isEscalateStage(stage: Stage): boolean {
  return ESCALATE_STAGES.has(stage);
}
