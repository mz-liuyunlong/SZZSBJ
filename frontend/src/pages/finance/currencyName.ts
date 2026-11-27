/**
 * 财务页面上的币种一律写中文（Rocky 2026-11-05）：CNY、CNH、RMB 都写「人民币」，USD 写「美元」。
 * 只改显示；数据库和接口里的币种代码不变。
 */
const NAMES: Record<string, string> = { CNY: "人民币", CNH: "人民币", RMB: "人民币", USD: "美元" };

export const isRmb = (code: string | null | undefined) => code === "CNY" || code === "CNH" || code === "RMB";

export const currencyName = (code: string | null | undefined): string => (code ? NAMES[code] ?? code : "");

/** 账户名、异常说明这类文字里混着币种代码的，也换成中文。只换独立的代码，不碰别的英文。 */
export const currencyText = (text: string): string =>
  text.replace(/(?<![A-Za-z0-9])(CNY|CNH|RMB|USD)(?![A-Za-z0-9])/g, (code) => NAMES[code]);
