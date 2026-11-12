/**
 * 审批单事由 / 明细里的银行卡号（Rocky 11-12）：员工在飞书里自己手写，没有单独的卡号字段，只能在这两段文字里认。
 * 系统里存完整卡号；页面默认只露后 4 位，详情里点小眼睛看全号（有日记账板块权限的人都能点）。
 * 认卡号的规则：13～19 位数字（银行卡号的长度），中间可以有空格或横线，并且通过 Luhn 校验位（所有银行卡号都满足，
 * 随手一串数字九成过不了）。只认事由和明细，单号、金额等有自己字段的不碰。
 */
const CANDIDATE = /(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)/g;

export function luhnOk(digits: string): boolean {
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

const isCard = (raw: string) => {
  const digits = raw.replace(/\D/g, "");
  return digits.length >= 13 && digits.length <= 19 && luhnOk(digits);
};

/** 把卡号除后 4 位外的数字换成 *，空格 / 横线保留：4662 4537 5286 6816 → **** **** **** 6816。 */
export function maskCards(text: string): string {
  return text.replace(CANDIDATE, (raw) => {
    if (!isCard(raw)) return raw;
    let keep = 4;
    return raw.split("").reverse().map((char) => {
      if (!/\d/.test(char)) return char;
      if (keep > 0) { keep -= 1; return char; }
      return "*";
    }).reverse().join("");
  });
}

export const hasCard = (text: string) => maskCards(text) !== text;
