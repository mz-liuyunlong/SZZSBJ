/**
 * Business-facing anomaly explanations. This is presentation guidance only:
 * it never certifies data, modifies facts, or authorizes a financial replay.
 */
export interface AnomalyGuideInput {
  error_code: string;
  details?: Record<string, unknown> | null;
}

export interface AnomalyGuide {
  title: string;
  explanation: string;
  checks: readonly string[];
  requiredEvidence: readonly string[];
  safeNextStep: string;
  category: "sample" | "advertising" | "technical" | "other";
  comparison?: string;
}

function numeric(value: unknown): number | null {
  if (typeof value !== "string" && typeof value !== "number") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function units(value: number): string {
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
}

function dollars(value: number): string {
  return "$" + value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function describeSyncAnomaly(input: AnomalyGuideInput): AnomalyGuide {
  const d = input.details ?? {};
  if (input.error_code === "DATA_PAGES_CONFIRMED_SAMPLE_EXCEEDS_SALESTAT") {
    const sampleQty = numeric(d.sku_day_sample_qty);
    const salesQty = numeric(d.sku_day_salestat_qty);
    const sampleAmount = numeric(d.sku_day_sample_reference_amount);
    const salesAmount = numeric(d.sku_day_salestat_sales);
    const parts: string[] = [];
    if (sampleQty !== null && salesQty !== null) {
      parts.push("送样 " + units(sampleQty) + " 件，SaleStat " +
        units(salesQty) + " 件（差 " + units(sampleQty - salesQty) + " 件）");
    }
    if (sampleAmount !== null && salesAmount !== null) {
      parts.push("送样参考金额 " + dollars(sampleAmount) +
        "，SaleStat " + dollars(salesAmount));
    }
    return {
      title: "送样数量或金额与销售统计对不上",
      category: "sample",
      comparison: parts.length ? parts.join("；") : undefined,
      explanation: "同店铺、同商品、同一天已认定的送样，合计数量或参考金额高于 SaleStat。订单是否为0元送样与能否从销售统计中安全扣减是两回事；这里不能直接删送样，也不能强行扣减利润。",
      checks: [
        "先核对订单实付是否为0、是否取消；同一订单不要重复计算。",
        "核对订单的美国业务日期和 SaleStat 日期，注意跨日订单。",
        "确认 SaleStat 是否包含0元送样；如本来不包含，不必强行让两边数字相等。",
      ],
      requiredEvidence: [
        "Walmart 或领星订单号与0元支付、取消状态的凭据",
        "SaleStat 对应日期、店铺、商品的数量和金额凭据",
        "如果统计口径不同，写明 SaleStat 是否包括0元送样及核对依据",
      ],
      safeNextStep: "先记录核对结论。需要修改销售或利润时，必须等财务重算接口及复验功能接通，不能靠改状态完成。",
    };
  }
  if (input.error_code === "FINANCE_SEM_CAMPAIGN_SPEND_UNALLOCATED" ||
    input.error_code === "DATA_PAGES_SEM_SPEND_UNATTRIBUTED") {
    return {
      title: "SEM 广告花费暂时无法分配到商品",
      category: "advertising",
      explanation: "系统拿到了某个 Campaign 的广告花费，但没有足够可靠的信息确认应算到哪个商品。花费不是消失了，而是尚未能安全归属，可能影响商品利润。",
      checks: [
        "按异常日期和店铺在广告报表中查找 Campaign。",
        "确认该广告活动实际推广哪些商品，是否跨多个 Item ID。",
        "核对广告金额、币种及日期；不可仅从 Campaign 名称猜商品编号。",
      ],
      requiredEvidence: [
        "Campaign ID / 名称及对应日期和店铺",
        "广告报表花费、币种与商品 Item ID 的实际对应依据",
        "若是多商品活动，提供明确的分摊依据，不要随意平均分",
      ],
      safeNextStep: "有可靠商品归属后登记待修复；归属与费用计算必须经过单独的安全重算，记录备注不会改动广告费。",
    };
  }
  if (input.error_code === "FINANCE_SP_SPEND_UNALLOCATED") {
    return {
      title: "SP 广告费用无法归属到商品",
      category: "advertising",
      explanation: "SP 广告花费已记录，但对应商品身份或店铺、日期的数据无法可靠匹配，因此还不能正确分配到商品利润。",
      checks: [
        "按日期、店铺查 SP 广告报表。",
        "核对被推广商品 Item ID、广告活动和金额。",
        "若商品改过编号或有多个匹配结果，提供实际对应关系。",
      ],
      requiredEvidence: [
        "SP 广告报表中的日期、店铺、Item ID",
        "实际花费和币种、对应 Campaign 或广告标识",
      ],
      safeNextStep: "确认准确归属后登记待修复。暂不直接改动订单、广告费或利润事实表。",
    };
  }
  if (input.error_code === "DATA_PAGES_SAMPLE_RULE_VERSION_UNSUPPORTED") {
    return {
      title: "送样使用了系统不支持的旧规则",
      category: "sample",
      explanation: "有一笔已标记送样的历史记录使用了尚未被当前规则认可的版本，系统为避免错误扣减而停止计算。",
      checks: ["核对订单支付金额和取消状态。", "核对该记录的历史批准依据。"],
      requiredEvidence: ["订单号、平台支付金额、取消状态及历史批准记录"],
      safeNextStep: "提交证据给技术复验，不要批量修改送样标记或规则版本。",
    };
  }
  if (input.error_code === "SYNC_EXECUTION_FAILED") {
    return {
      title: "同步任务执行失败",
      category: "technical",
      explanation: "这是数据同步过程中出现的技术故障，未必存在订单或费用错误。",
      checks: ["查看关联任务的执行日志与失败日期。", "核对是否已有新一轮成功同步。"],
      requiredEvidence: ["任务 Run ID 和失败日志中的错误信息"],
      safeNextStep: "技术人员确认原因后再按任务范围重试；不要因为任务失败而手工补销售或利润。",
    };
  }
  return {
    title: "需要核对的数据异常",
    category: "other",
    explanation: "系统记录了异常，但暂时没有针对该错误码的专属自动修复流程，不能单凭错误码推断数据应该怎样改。",
    checks: ["核对日期、店铺、商品及原始业务记录。", "保存具体差异和证据，交由对应业务负责人处理。"],
    requiredEvidence: ["具体业务日期、关联订单或活动、来源报表和核对结果"],
    safeNextStep: "先记录核对过程；无法判断时保留待核对，不要手工改动财务数据。",
  };
}
