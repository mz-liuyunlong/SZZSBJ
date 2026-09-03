/**
 * src/ai_pmc/aiEvaluate.ts
 * Phase 8 — 单个 ItemID 的补货 AI 评估
 *
 * 复用 .env：AI_BASE_URL / AI_MODEL / AI_API_KEY（OpenAI 兼容 chat/completions）。
 * 铁律：超时或任何异常 → catch 返回 fallback，记日志，不抛出、不重试。
 */

process.env.TZ = 'Asia/Shanghai';

import 'dotenv/config';
import { ReplenishTask, AiEvalResult } from './calcReplenishment';
import { logger } from './logger';

const axios = require('axios/dist/node/axios.cjs') as typeof import('axios').default;

const AI_BASE_URL = (process.env.AI_BASE_URL ?? '').trim().replace(/\/+$/, '');
const AI_MODEL = (process.env.AI_MODEL ?? 'gpt-5.4').trim();
const AI_API_KEY = (process.env.AI_API_KEY ?? '').trim();

const SYSTEM_PROMPT =
  '你是一个跨境电商补货分析师，帮助运营团队评估亚马逊/沃尔玛产品的补货需求。分析要简洁直接，给出可执行结论，避免废话。';

function buildUserPrompt(t: ReplenishTask): string {
  return [
    '请分析以下产品的补货情况：',
    `产品：${t.productName}（${t.itemId}）`,
    `近15天日均：${t.avgDaily15}件/天`,
    `近30天日均：${t.avgDaily30}件/天`,
    `去年同期日均：${t.yoyAvgDaily}件/天（同比系数${t.yoyRatio}）`,
    `是否Q4旺季：${t.isQ4 ? '是' : '否'}（Q4已按倍数估算）`,
    `调整后日均：${t.adjustedAvg}件/天`,
    `当前总库存：${t.totalInventory}件`,
    `  └ 国内仓：${t.domestic}件`,
    `  └ 采购未到货：${t.purchasePending}件`,
    `  └ 发往在途：${t.inTransit}件`,
    `  └ 海外在库：${t.overseas}件`,
    `目标库存：${t.targetInventory}件`,
    `系统建议补货：${t.suggestQty}件`,
    '近3次补货记录：无',
    '',
    '严格按以下JSON格式返回，不输出任何其他内容：',
    '{',
    '  "priority": "高|中|低",',
    '  "adjustedSuggestQty": 数字,',
    '  "reason": "调整原因（一句话）",',
    '  "analysis": "综合分析（2-3句，含季节性判断和风险提示）"',
    '}',
  ].join('\n');
}

function fallback(t: ReplenishTask): AiEvalResult {
  return {
    priority: '中',
    adjustedSuggestQty: t.suggestQty,
    reason: 'AI评估不可用，使用系统计算结果',
    analysis: `系统计算：日均${t.adjustedAvg}件，当前库存${t.totalInventory}件，建议补货${t.suggestQty}件`,
    aiSuccess: false,
  };
}

function parseAi(content: string, t: ReplenishTask): AiEvalResult {
  // 容错：从返回里抽取第一个 JSON 对象
  const m = content.match(/\{[\s\S]*\}/);
  if (!m) throw new Error('AI返回无JSON');
  const obj = JSON.parse(m[0]) as Record<string, unknown>;
  const qty = Number(obj.adjustedSuggestQty);
  return {
    priority: String(obj.priority ?? '中').trim() || '中',
    adjustedSuggestQty: Number.isFinite(qty) ? Math.round(qty) : t.suggestQty,
    reason: String(obj.reason ?? '').trim() || '（无）',
    analysis: String(obj.analysis ?? '').trim() || '（无）',
    aiSuccess: true,
  };
}

/** 评估单个 ItemID；任何失败均返回 fallback，不抛出。 */
export async function aiEvaluate(task: ReplenishTask, timeoutMs: number): Promise<AiEvalResult> {
  if (!AI_BASE_URL || !AI_API_KEY) {
    logger.warn(`[aiEvaluate] 缺少 AI_BASE_URL/AI_API_KEY，ItemID=${task.itemId} 使用系统结果`);
    return fallback(task);
  }
  try {
    const resp = await axios.post(
      `${AI_BASE_URL}/chat/completions`,
      {
        model: AI_MODEL,
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: buildUserPrompt(task) },
        ],
        temperature: 0.3,
      },
      { headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${AI_API_KEY}` }, timeout: timeoutMs },
    );
    const content = String((resp.data as any)?.choices?.[0]?.message?.content ?? '').trim();
    if (!content) throw new Error('AI返回空内容');
    return parseAi(content, task);
  } catch (e) {
    logger.warn(`[aiEvaluate] AI评估失败，ItemID=${task.itemId}，原因=${e instanceof Error ? e.message : String(e)}，使用系统计算结果`);
    return fallback(task);
  }
}
