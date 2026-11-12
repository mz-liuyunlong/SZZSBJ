/**
 * 审批单事由 / 明细里的银行卡号（Rocky 11-12）：员工在飞书里自己手写，没有单独的卡号字段，只能在这两段文字里认。
 * 系统里存完整卡号；页面默认只露后 4 位，详情里点小眼睛看全号（有日记账板块权限的人都能点）。
 * 认卡号的规则：13～19 位数字（银行卡号的长度），中间可以有空格或横线，并且通过 Luhn 校验位（所有银行卡号都满足，
 * 随手一串数字九成过不了）。只认事由、明细、意见、评论这些手写文字，单号、金额等有自己字段的不碰。
 * 卡号前后常挨着金额、日期（「4111 1111 1111 1111 10元」）：按空格、横线、点、斜杠分组（全角也算），在一串数字里找能凑成卡号的
 * 连续几组，优先 16 位、再 19 / 15 / 18 / 17 / 14 / 13 位，找到就只打码这几组，前后的金额日期原样留着（刘云龙 #341 P1）。
 * 前面写了「卡号 / 银行卡 / 账号」的，过不了 Luhn 也按卡号打码（有的老卡号不带校验位）。
 */
/* 数字含全角（０-９）；分隔符 = 一个或多个半角空格、全角空格、横线、点、斜杠（「4111 - 1111」「4111.1111」「4111／1111」也能认），
   切开后分隔符原样保留（刘云龙 #341 补）。 */
const DIGIT = "0-9\uFF10-\uFF19";
const SEP = " \u3000\\-./\uFF0F";
const RUN = new RegExp(`(?<![${DIGIT}])[${DIGIT}]+(?:[${SEP}]+[${DIGIT}]+)*(?![${DIGIT}])`, "g");
const SEP_SPLIT = new RegExp(`([${SEP}]+)`);
const CARD_HINT = /(卡号|银行卡|账号|帐号|card\s*(?:no|number|#)?)\s*(?:是|为)?\s*[:：]?\s*$/i;

/** 全角数字换成半角，只用于识别和校验；显示仍按原文打码。 */
const toHalf = (text: string) => text.replace(/[\uFF10-\uFF19]/g, (char) => String.fromCharCode(char.charCodeAt(0) - 0xfee0));
const PREFERRED_LENGTHS = [16, 19, 15, 18, 17, 14, 13];

export function luhnOk(raw: string): boolean {
  const digits = toHalf(raw);
  let sum = 0;
  for (let index = 0; index < digits.length; index += 1) {
    let digit = Number(digits[digits.length - 1 - index]);
    if (index % 2 === 1) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    sum += digit;
  }
  return sum % 10 === 0;
}

/** 从 start 组开始、正好凑成 length 位的结束组下标；凑不出来返回 -1。 */
function endFor(groups: string[], start: number, length: number): number {
  let total = 0;
  for (let end = start; end < groups.length; end += 1) {
    total += groups[end].length;
    if (total === length) return end;
    if (total > length) return -1;
  }
  return -1;
}

/** 像卡号的写法：一整串不分组，或 4-4-4-4（最后一组可以是 1～4 位，19 位卡），或 4-6-5 / 4-6-4（美国运通 / 大来）。 */
function cardShaped(groups: string[]): boolean {
  if (groups.length === 1) return true;
  const sizes = groups.map((group) => group.length);
  if (sizes.slice(0, -1).every((size) => size === 4) && sizes[sizes.length - 1] <= 4) return true;
  return sizes.length === 3 && sizes[0] === 4 && sizes[1] === 6 && (sizes[2] === 5 || sizes[2] === 4);
}

/** 一串数字里认出的卡号：[开始组, 结束组]。候选是过 Luhn、长度 13～19 的连续几组，并且像卡号的写法；
 * 前面有「卡号 / 银行卡 / 账号」提示词的，任意分组过 Luhn 都算（如「卡号 622202 1234567894」）。
 * 先挑像卡号写法的，再按长度优先级，互不重叠地挑（「2026-10-30 4111 1111 1111 1111」不会把日期和卡号拼成一个）。
 * 一个都没有、前面又写了「卡号」的，取第一个像卡号写法的。 */
function cardSpans(groups: string[], hinted: boolean): [number, number][] {
  const candidates: { start: number; end: number; rank: number }[] = [];
  PREFERRED_LENGTHS.forEach((length, order) => {
    for (let start = 0; start < groups.length; start += 1) {
      const end = endFor(groups, start, length);
      if (end < 0) continue;
      const window = groups.slice(start, end + 1);
      if (!luhnOk(window.join(""))) continue;
      const shaped = cardShaped(window);
      // 没有提示词时只认像卡号的写法：点号、斜杠也算分隔符后，金额列表、日期区间偶尔能凑出过 Luhn 的数字（刘云龙 #341 审核）
      if (!shaped && !hinted) continue;
      candidates.push({ start, end, rank: (shaped ? 0 : 100) + order });
    }
  });
  candidates.sort((a, b) => a.rank - b.rank || a.start - b.start);
  const spans: [number, number][] = [];
  for (const { start, end } of candidates) {
    if (spans.every(([a, b]) => end < a || start > b)) spans.push([start, end]);
  }
  if (!spans.length && hinted) {
    for (const length of PREFERRED_LENGTHS) {
      for (let start = 0; start < groups.length; start += 1) {
        const end = endFor(groups, start, length);
        if (end >= 0 && cardShaped(groups.slice(start, end + 1))) return [[start, end]];
      }
    }
  }
  return spans;
}

function maskGroups(groups: string[], start: number, end: number): string[] {
  let keep = 4;
  const out = [...groups];
  for (let index = end; index >= start; index -= 1) {
    out[index] = groups[index].split("").reverse().map((char) => {
      if (keep > 0) { keep -= 1; return char; }
      return "*";
    }).reverse().join("");
  }
  return out;
}

/** 把卡号除后 4 位外的数字换成 *，空格 / 横线和前后的金额日期保留：「4662 4537 5286 6816 10元」→「**** **** **** 6816 10元」。 */
export function maskCards(text: string): string {
  return text.replace(RUN, (run: string, offset: number) => {
    const pieces = run.split(SEP_SPLIT);
    let groups = pieces.filter((_, index) => index % 2 === 0);
    const hinted = CARD_HINT.test(text.slice(Math.max(0, offset - 12), offset));
    const spans = cardSpans(groups.map(toHalf), hinted);
    if (!spans.length) return run;
    for (const [start, end] of spans) groups = maskGroups(groups, start, end);
    return pieces.map((piece, index) => (index % 2 === 0 ? groups[index / 2] : piece)).join("");
  });
}

export const hasCard = (text: string) => maskCards(text) !== text;
