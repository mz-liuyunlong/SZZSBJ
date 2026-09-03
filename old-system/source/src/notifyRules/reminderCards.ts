/**
 * reminderCards.ts - 日常提醒飞书交互卡片构建（纯函数，零外部调用）
 *
 * 背景（2026-07-18 需求方指令）：各提醒要有辨识度的专属名称（对齐"📊 业绩日报"风格），
 * 且内容必须按负责人清晰分组，不能杂乱。
 *
 * 本模块只负责"数据→卡片JSON+纯文本降级"，发送由各脚本走 feishuNotify.sendCardWithFallbackToChat。
 * 卡片命名约定：emoji + 专属名称 + " ｜ " + 日期，如：
 *   📉 低利润产品提醒 ｜ 2026-07-18   （2026-07-18 需求方定名，原"产品规则信号日报"）
 *   🙋 待认领产品日报 ｜ 2026-07-18
 *   🔻 订单异常下滑提醒 ｜ 2026-07-18
 */

export interface CardBundle {
  title: string;
  card: Record<string, unknown>;
  fallbackText: string;
}

export interface RuleSignalItem {
  owner: string;          // 空串=未分配
  storeName: string;
  itemId: string;
  msku: string;
  ruleLevel: string;
  ruleName: string;
  triggerReason: string;
  suggestedAction: string;
  isNew: boolean;         // 本批新触发
}

export interface UnmatchedOwnerItem {
  storeName: string;
  itemId: string;
  msku: string;
}

/** rule_level → 视觉标记 */
export function levelBadge(level: string): string {
  const l = (level ?? "").toLowerCase();
  if (/high|error|严重|高/.test(l)) return "🔴";
  if (/warn|medium|中/.test(l)) return "🟡";
  if (/info|low|低|提示/.test(l)) return "🔵";
  return "▫️";
}

function esc(s: unknown): string {
  return String(s ?? "").trim() || "-";
}

function groupByOwner(items: RuleSignalItem[]): Map<string, RuleSignalItem[]> {
  const m = new Map<string, RuleSignalItem[]>();
  for (const it of items) {
    const key = (it.owner ?? "").trim() || "（未分配负责人）";
    if (!m.has(key)) m.set(key, []);
    m.get(key)!.push(it);
  }
  return m;
}

/**
 * 🚦 产品规则信号日报卡片
 * - 橙色头（警示类）；负责人一人一个分区（加粗姓名+条数），分区间分割线
 * - perOwnerLimit 内逐条展开，超出折叠为"另有N条"
 */
export function buildRuleSignalCard(
  signalDate: string,
  items: RuleSignalItem[],
  opts: { perOwnerLimit: number; pageUrl: string; testPrefix?: boolean },
): CardBundle {
  const byOwner = groupByOwner(items);
  const products = new Set(items.map((s) => `${s.itemId}|${s.msku}`));
  const prefix = opts.testPrefix ? "【测试】" : "";
  const title = `${prefix}📉 低利润产品提醒 ｜ ${signalDate}`;

  const elements: Record<string, unknown>[] = [
    {
      tag: "div",
      text: {
        tag: "lark_md",
        content: `**本次信号** ${items.length} 条　·　**涉及负责人** ${byOwner.size} 人　·　**涉及产品** ${products.size} 个`,
      },
    },
    { tag: "hr" },
  ];

  const fb: string[] = [`${title}`, `本次信号 ${items.length} 条 ｜ 负责人 ${byOwner.size} ｜ 产品 ${products.size}`];

  for (const [owner, list] of byOwner) {
    const lines: string[] = [`**👤 ${owner}**　（${list.length} 条）`];
    fb.push("", `负责人：${owner}（${list.length} 条）`);
    list.slice(0, opts.perOwnerLimit).forEach((s, i) => {
      const nu = s.isNew ? " 🆕" : "";
      lines.push(
        `**${i + 1}. ${esc(s.storeName)} ｜ ${esc(s.msku)}**${nu}`,
        `${levelBadge(s.ruleLevel)} ${esc(s.ruleName)}：${esc(s.triggerReason)}`,
        `↳ 建议：${esc(s.suggestedAction) === "-" ? "暂无系统规则建议" : esc(s.suggestedAction)}`,
      );
      fb.push(`${i + 1}. ${s.isNew ? "[新] " : ""}${esc(s.storeName)} ｜ ItemID ${esc(s.itemId)} ｜ MSKU ${esc(s.msku)}`,
        `   [${esc(s.ruleLevel)}] ${esc(s.ruleName)}：${esc(s.triggerReason)}`);
    });
    if (list.length > opts.perOwnerLimit) {
      lines.push(`…另有 ${list.length - opts.perOwnerLimit} 条未展开，请到页面查看`);
      fb.push(`   …另有 ${list.length - opts.perOwnerLimit} 条未展开`);
    }
    elements.push({ tag: "div", text: { tag: "lark_md", content: lines.join("\n") } });
    elements.push({ tag: "hr" });
  }

  elements.push({
    tag: "action",
    actions: [
      {
        tag: "button",
        text: { tag: "plain_text", content: "打开产品管理页面" },
        type: "primary",
        url: opts.pageUrl,
      },
    ],
  });
  elements.push({
    tag: "note",
    elements: [{ tag: "plain_text", content: "同一信号按规则自带频率去重，持续存在每 N 天提醒一次；🆕=本批新触发" }],
  });
  fb.push("", `页面：${opts.pageUrl}`);

  return {
    title,
    card: {
      config: { wide_screen_mode: true },
      header: { template: "orange", title: { tag: "plain_text", content: title } },
      elements,
    },
    fallbackText: fb.join("\n"),
  };
}

export interface OrderDropCardItem {
  owner: string;          // 空串=未匹配负责人
  storeName: string;
  itemId: string;
  msku: string;
  productName: string;
  detail: string;         // 预格式化：近3天订单 x/y/z（日均a）→ 当日 b ↓c%
  streak: string;         // 预格式化：连续第N天异常
}

/**
 * 🔻 订单异常下滑提醒卡片
 * - 红色头（异常类）；负责人一人一个分区，分区间分割线（与待认领日报同风格）
 */
export function buildOrderDropCard(
  dataDate: string,
  items: OrderDropCardItem[],
  opts: { testPrefix?: boolean },
): CardBundle {
  const prefix = opts.testPrefix ? "【测试】" : "";
  const title = `${prefix}🔻 订单异常下滑提醒 ｜ ${dataDate}`;

  const byOwner = new Map<string, OrderDropCardItem[]>();
  for (const it of items) {
    const key = (it.owner ?? "").trim() || "（未匹配负责人）";
    if (!byOwner.has(key)) byOwner.set(key, []);
    byOwner.get(key)!.push(it);
  }

  const elements: Record<string, unknown>[] = [
    {
      tag: "div",
      text: {
        tag: "lark_md",
        content: `**数据日期** ${dataDate}　·　**异常产品** ${items.length} 个　·　**涉及负责人** ${byOwner.size} 人`,
      },
    },
    { tag: "hr" },
  ];
  const fb: string[] = [title, `数据日期 ${dataDate} ｜ 异常产品 ${items.length} ｜ 负责人 ${byOwner.size}`];

  for (const [owner, list] of byOwner) {
    const lines: string[] = [`**👤 ${owner}**　（${list.length} 个异常）`];
    fb.push("", `负责人：${owner}（${list.length} 个异常）`);
    list.forEach((it, i) => {
      lines.push(
        `**${i + 1}. ${esc(it.storeName)} ｜ ${esc(it.msku)}**${it.productName ? ` ${it.productName}` : ""}`,
        `${esc(it.detail)}`,
        `↳ ${esc(it.streak)}`,
      );
      fb.push(`${i + 1}. ItemID：${esc(it.itemId)} ｜ 店铺：${esc(it.storeName)} ｜ MSKU：${esc(it.msku)}`,
        `   ${esc(it.detail)}`, `   ${esc(it.streak)}`);
    });
    elements.push({ tag: "div", text: { tag: "lark_md", content: lines.join("\n") } });
    elements.push({ tag: "hr" });
  }
  elements.push({
    tag: "note",
    elements: [{ tag: "plain_text", content: "口径：16:25 拉当日销量，按 7 档分级规则判定；断货/CS测品/归档已剔除" }],
  });

  return {
    title,
    card: {
      config: { wide_screen_mode: true },
      header: { template: "red", title: { tag: "plain_text", content: title } },
      elements,
    },
    fallbackText: fb.join("\n"),
  };
}

export interface ClearanceApprovalItem {
  id: number;
  storeName: string;
  itemId: string;
  mskus: string;
  sku: string;
  owner: string;
  applicant: string;
  sales30: number;
  stock: number;
  inbound: number;
  turnoverDays: number | null;
}

/**
 * 🧹 清货申请审批汇总卡（批①，2026-07-20 需求方确认格式）
 * 每天 09:33 一张卡发审批人；每个申请一个分区，各带【同意清货】【驳回】按钮；
 * testMode=true 时按钮 value 带 test=1（回调只应答不落库）。
 */
export function buildClearanceApprovalCard(
  dateStr: string,
  items: ClearanceApprovalItem[],
  opts: { testMode?: boolean },
): CardBundle {
  const prefix = opts.testMode ? "【测试】" : "";
  const title = `${prefix}🧹 清货申请审批 ｜ ${dateStr}（${items.length} 项待审批）`;
  const applicants = new Set(items.map((i) => i.applicant));

  const elements: Record<string, unknown>[] = [
    {
      tag: "div",
      text: {
        tag: "lark_md",
        content: `今日待审批 **${items.length}** 个 ItemID　·　申请人 ${applicants.size} 人　·　逐条审批，点过即生效`,
      },
    },
    { tag: "hr" },
  ];
  const fb: string[] = [title, `待审批 ${items.length} 项（卡片发送失败降级为本文本，无法按钮审批，次日 09:33 自动重发卡片）`];

  items.forEach((it, i) => {
    const turnover = it.turnoverDays === null ? "—" : `${it.turnoverDays} 天`;
    const info = `**${i + 1}. ${esc(it.storeName)} ｜ ${esc(it.mskus)}**\n` +
      `ItemID ${esc(it.itemId)} · 申请人 ${esc(it.applicant)} · 负责人 ${esc(it.owner)}\n` +
      `近30天销量 ${it.sales30} · 库存 ${it.stock} · 在途 ${it.inbound} · 周转 ${turnover}`;
    elements.push({ tag: "div", text: { tag: "lark_md", content: info } });
    elements.push({
      tag: "action",
      actions: [
        {
          tag: "button",
          text: { tag: "plain_text", content: "同意清货" },
          type: "primary",
          value: { biz: "clearance_approval", id: it.id, choice: "approve", ...(opts.testMode ? { test: 1 } : {}) },
        },
        {
          tag: "button",
          text: { tag: "plain_text", content: "驳回" },
          type: "danger",
          value: { biz: "clearance_approval", id: it.id, choice: "reject", ...(opts.testMode ? { test: 1 } : {}) },
        },
      ],
    });
    elements.push({ tag: "hr" });
    fb.push(`${i + 1}. ${esc(it.storeName)} ｜ ${esc(it.mskus)} ｜ ItemID ${esc(it.itemId)} ｜ 申请人 ${esc(it.applicant)} ｜ 销量30d ${it.sales30} ｜ 库存 ${it.stock} ｜ 在途 ${it.inbound}`);
  });

  elements.push({
    tag: "note",
    elements: [{ tag: "plain_text", content: "审批通过后该 ItemID 进入清货期（不联动其他变体）· 未处理的申请明天 09:33 重新出现" }],
  });

  return {
    title,
    card: {
      config: { wide_screen_mode: true },
      header: { template: "amber", title: { tag: "plain_text", content: title } },
      elements,
    },
    fallbackText: fb.join("\n"),
  };
}

// ── 清货三张自动卡（批③，2026-07-21 需求方定稿）────────────────────────────
export interface ClearanceTailItem {
  id: number;            // event_clearance_card.id（按钮回调用）
  storeName: string;
  itemId: string;
  mskus: string;
  stock: number;
  daily7: number;
  daysToClear: number;
  expectEnd: string;     // 人工预计清货结束时间，空=未设置
}

/**
 * 🧹 清货收尾确认卡（周五10:16，按负责人一人一卡）
 * 触发：清货中且库存≤60天可卖量；【继续清货】=14天内不再问；【转稳定期】=出清货期
 */
export function buildClearanceTailCard(
  dateStr: string,
  ownerName: string,
  items: ClearanceTailItem[],
  opts: { testMode?: boolean },
): CardBundle {
  const prefix = opts.testMode ? "【测试】" : "";
  const title = `${prefix}🧹 清货收尾确认 ｜ ${dateStr}（${items.length} 个产品）`;
  const elements: Record<string, unknown>[] = [
    {
      tag: "div",
      text: { tag: "lark_md", content: `**${ownerName}**，以下清货产品库存已清到 60 天可卖量以内，请逐个确认：继续清还是转回稳定期` },
    },
    { tag: "hr" },
  ];
  const fb: string[] = [title, `负责人 ${ownerName} ｜ ${items.length} 个产品待确认（卡片失败降级文本无法操作，下周五重发）`];
  items.forEach((it, i) => {
    elements.push({
      tag: "div",
      text: {
        tag: "lark_md",
        content: `**${i + 1}. ${esc(it.storeName)} ｜ ${esc(it.mskus)}**\n` +
          `ItemID ${esc(it.itemId)} · 库存 ${it.stock} · 7日日销 ${it.daily7} · 约 ${it.daysToClear} 天清完` +
          (it.expectEnd ? ` · 预计结束 ${it.expectEnd}` : ""),
      },
    });
    elements.push({
      tag: "action",
      actions: [
        { tag: "button", text: { tag: "plain_text", content: "继续清货" }, type: "default",
          value: { biz: "clearance_card", id: it.id, choice: "continue", ...(opts.testMode ? { test: 1 } : {}) } },
        { tag: "button", text: { tag: "plain_text", content: "转稳定期" }, type: "primary",
          value: { biz: "clearance_card", id: it.id, choice: "stable", ...(opts.testMode ? { test: 1 } : {}) } },
      ],
    });
    elements.push({ tag: "hr" });
    fb.push(`${i + 1}. ${esc(it.storeName)} ｜ ${esc(it.mskus)} ｜ 库存${it.stock} ｜ 约${it.daysToClear}天清完`);
  });
  elements.push({
    tag: "note",
    elements: [{ tag: "plain_text", content: "点【继续清货】14天内不再询问该产品；点【转稳定期】立即生效并移出清货中心" }],
  });
  return {
    title,
    card: { config: { wide_screen_mode: true }, header: { template: "turquoise", title: { tag: "plain_text", content: title } }, elements },
    fallbackText: fb.join("\n"),
  };
}

export interface ClearanceArchiveItem {
  id: number;
  storeName: string;
  itemId: string;
  mskus: string;
  zeroDays: number;
}

/** 📦 清货完成·归档确认卡（清零满7天，一品一卡发负责人） */
export function buildClearanceArchiveCard(item: ClearanceArchiveItem, opts: { testMode?: boolean }): CardBundle {
  const prefix = opts.testMode ? "【测试】" : "";
  const title = `${prefix}📦 清货完成·归档确认 ｜ ${esc(item.mskus)}`;
  const elements: Record<string, unknown>[] = [
    {
      tag: "div",
      text: {
        tag: "lark_md",
        content: `**${esc(item.storeName)} ｜ ${esc(item.mskus)}**\nItemID ${esc(item.itemId)}\n` +
          `库存与在途已清零 **${item.zeroDays} 天**，是否归档？`,
      },
    },
    {
      tag: "action",
      actions: [
        { tag: "button", text: { tag: "plain_text", content: "确认归档" }, type: "primary",
          value: { biz: "clearance_card", id: item.id, choice: "archive", ...(opts.testMode ? { test: 1 } : {}) } },
        { tag: "button", text: { tag: "plain_text", content: "暂不归档（7天后再问）" }, type: "default",
          value: { biz: "clearance_card", id: item.id, choice: "later", ...(opts.testMode ? { test: 1 } : {}) } },
      ],
    },
    {
      tag: "note",
      elements: [{ tag: "plain_text", content: "确认归档走审计与库存拦截链路：若期间冒出库存/在途会被系统拦下并提示" }],
    },
  ];
  return {
    title,
    card: { config: { wide_screen_mode: true }, header: { template: "green", title: { tag: "plain_text", content: title } }, elements },
    fallbackText: `${title}\n${item.storeName} ｜ ItemID ${item.itemId} ｜ 清零 ${item.zeroDays} 天（卡片失败降级文本无法操作，7天后重发）`,
  };
}

export interface ClearanceReviveItem {
  id: number;
  storeName: string;
  itemId: string;
  mskus: string;
  shipmentId: string;
  shipmentQty: number;
  sourceLabel?: string;   // 默认"新货件"；批④采购触发传"新采购单"
}

/** 🔄 清货产品新货件确认卡（清货期产品出现新货件，一件一卡发负责人，只有两个去向） */
export function buildClearanceReviveCard(item: ClearanceReviveItem, opts: { testMode?: boolean }): CardBundle {
  const prefix = opts.testMode ? "【测试】" : "";
  const title = `${prefix}🔄 清货产品有新货件 ｜ ${esc(item.mskus)}`;
  const elements: Record<string, unknown>[] = [
    {
      tag: "div",
      text: {
        tag: "lark_md",
        content: `**${esc(item.storeName)} ｜ ${esc(item.mskus)}**\nItemID ${esc(item.itemId)}\n` +
          `该产品处于清货期，但检测到${item.sourceLabel ?? "新货件"} **${esc(item.shipmentId)}**（${item.shipmentQty} 件）。\n` +
          `既然要补货，请确认生命周期去向：`,
      },
    },
    {
      tag: "action",
      actions: [
        { tag: "button", text: { tag: "plain_text", content: "转上升期" }, type: "primary",
          value: { biz: "clearance_card", id: item.id, choice: "rising", ...(opts.testMode ? { test: 1 } : {}) } },
        { tag: "button", text: { tag: "plain_text", content: "转稳定期" }, type: "default",
          value: { biz: "clearance_card", id: item.id, choice: "stable", ...(opts.testMode ? { test: 1 } : {}) } },
      ],
    },
    {
      tag: "note",
      elements: [{ tag: "plain_text", content: "点击即生效并移出清货中心；不处理则产品保持清货期（每个货件只提醒一次）" }],
    },
  ];
  return {
    title,
    card: { config: { wide_screen_mode: true }, header: { template: "violet", title: { tag: "plain_text", content: title } }, elements },
    fallbackText: `${title}\n${item.storeName} ｜ ItemID ${item.itemId} ｜ 新货件 ${item.shipmentId}（${item.shipmentQty}件）（卡片失败降级文本无法操作）`,
  };
}

export interface OpsInactionCardItem {
  owner: string;              // 空串=未分配
  storeName: string;
  itemId: string;
  mskus: string;
  poolReason: string;         // 入池原因：5天不出单/D级 等
  ruleHit: string;            // 命中规则：连续5个日志日无动作
  lastActionDate: string | null;
}

/**
 * ⚠️ 无运营动作产品提醒卡片（2026-07-20 需求方指令：与"📉 低利润产品提醒"格式统一）
 * - 橙色头；负责人一人一个分区；行样式与低利润卡一致
 */
export function buildOpsInactionCard(
  dateStr: string,
  items: OpsInactionCardItem[],
  opts: { resolvedToday?: number; titleNote?: string; testPrefix?: boolean },
): CardBundle {
  const prefix = opts.testPrefix ? "【测试】" : "";
  const title = `${prefix}⚠️ 无运营动作产品提醒 ｜ ${dateStr}${opts.titleNote ?? ""}`;

  const byOwner = new Map<string, OpsInactionCardItem[]>();
  for (const it of items) {
    const key = (it.owner ?? "").trim() || "（未分配负责人）";
    if (!byOwner.has(key)) byOwner.set(key, []);
    byOwner.get(key)!.push(it);
  }
  const products = new Set(items.map((s) => `${s.itemId}|${s.mskus}`));

  const elements: Record<string, unknown>[] = [
    {
      tag: "div",
      text: {
        tag: "lark_md",
        content: `**本次通报** ${items.length} 条　·　**涉及负责人** ${byOwner.size} 人　·　**涉及产品** ${products.size} 个`
          + (opts.resolvedToday ? `　·　今日自动解除 ${opts.resolvedToday} 个` : ""),
      },
    },
    { tag: "hr" },
  ];
  const fb: string[] = [title, `本次通报 ${items.length} 条 ｜ 负责人 ${byOwner.size} ｜ 产品 ${products.size}`];

  for (const [owner, list] of byOwner) {
    const lines: string[] = [`**👤 ${owner}**　（${list.length} 条）`];
    fb.push("", `负责人：${owner}（${list.length} 条）`);
    list.forEach((s, i) => {
      const last = s.lastActionDate ? `（最近动作：${s.lastActionDate.slice(5)}）` : "";
      lines.push(
        `**${i + 1}. ${esc(s.storeName)} ｜ ${esc(s.mskus)}**`,
        `▫️ ${esc(s.poolReason)} ｜ ${esc(s.ruleHit)}${last}`,
      );
      fb.push(`${i + 1}. ${esc(s.storeName)} ｜ ItemID ${esc(s.itemId)} ｜ MSKU ${esc(s.mskus)}`,
        `   ${esc(s.poolReason)} ｜ ${esc(s.ruleHit)}${last}`);
    });
    elements.push({ tag: "div", text: { tag: "lark_md", content: lines.join("\n") } });
    elements.push({ tag: "hr" });
  }
  elements.push({
    tag: "note",
    elements: [{ tag: "plain_text", content: "规则：连续5个日志日无运营动作即通报（断货天数自动跳过）；填写实质运营日志当日自动解除" }],
  });
  fb.push("", "请今日处理并填写运营日志（填写实质内容当日自动解除）");

  return {
    title,
    card: {
      config: { wide_screen_mode: true },
      header: { template: "orange", title: { tag: "plain_text", content: title } },
      elements,
    },
    fallbackText: fb.join("\n"),
  };
}

/**
 * 🙋 待认领产品日报卡片（缺负责人）
 * - 紫色头；按店铺分组（该场景天然无负责人，用店铺分清楚归属）
 * - detailLimit 内展开，超出折叠；零缺失时输出绿色"全部已认领"卡
 */
export function buildUnmatchedOwnerCard(
  dateStr: string,
  activeTotal: number,
  items: UnmatchedOwnerItem[],
  opts: { detailLimit: number; pageUrl: string; testPrefix?: boolean },
): CardBundle {
  const prefix = opts.testPrefix ? "【测试】" : "";
  const title = `${prefix}🙋 待认领产品日报 ｜ ${dateStr}`;

  if (!items.length) {
    const text = `当前 active 商品 ${activeTotal} 个，全部已维护负责人 ✅`;
    return {
      title,
      card: {
        config: { wide_screen_mode: true },
        header: { template: "green", title: { tag: "plain_text", content: title } },
        elements: [
          { tag: "div", text: { tag: "lark_md", content: text } },
          {
            tag: "action",
            actions: [{ tag: "button", text: { tag: "plain_text", content: "打开产品管理页面" }, type: "default", url: opts.pageUrl }],
          },
        ],
      },
      fallbackText: `${title}\n${text}\n页面：${opts.pageUrl}`,
    };
  }

  const byStore = new Map<string, UnmatchedOwnerItem[]>();
  for (const it of items.slice(0, opts.detailLimit)) {
    const key = esc(it.storeName);
    if (!byStore.has(key)) byStore.set(key, []);
    byStore.get(key)!.push(it);
  }

  const elements: Record<string, unknown>[] = [
    {
      tag: "div",
      text: {
        tag: "lark_md",
        content: `**active 商品** ${activeTotal} 个　·　**缺负责人** ${items.length} 个`,
      },
    },
    { tag: "hr" },
  ];
  const fb: string[] = [title, `active 商品：${activeTotal} ｜ 缺负责人：${items.length}`];

  let seq = 0;
  for (const [store, list] of byStore) {
    const lines: string[] = [`**🏪 ${store}**　（${list.length} 个）`];
    fb.push("", `店铺：${store}（${list.length} 个）`);
    for (const it of list) {
      seq += 1;
      lines.push(`${seq}. ${esc(it.msku)} ｜ ItemID ${esc(it.itemId)}`);
      fb.push(`${seq}. MSKU：${esc(it.msku)} ｜ ItemID：${esc(it.itemId)}`);
    }
    elements.push({ tag: "div", text: { tag: "lark_md", content: lines.join("\n") } });
    elements.push({ tag: "hr" });
  }
  if (items.length > opts.detailLimit) {
    elements.push({
      tag: "div",
      text: { tag: "lark_md", content: `…其余 ${items.length - opts.detailLimit} 个请到产品管理页面查看` },
    });
    fb.push(`其余 ${items.length - opts.detailLimit} 个请到产品管理页面查看。`);
  }
  elements.push({
    tag: "action",
    actions: [{ tag: "button", text: { tag: "plain_text", content: "去认领负责人" }, type: "primary", url: opts.pageUrl }],
  });
  elements.push({
    tag: "note",
    elements: [{ tag: "plain_text", content: "口径：MySQL 产品管理 active 且负责人为空/未分配" }],
  });
  fb.push("", `页面：${opts.pageUrl}`);

  return {
    title,
    card: {
      config: { wide_screen_mode: true },
      header: { template: "purple", title: { tag: "plain_text", content: title } },
      elements,
    },
    fallbackText: fb.join("\n"),
  };
}
