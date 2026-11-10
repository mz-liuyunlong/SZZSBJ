import { describe, expect, it, vi } from "vitest";
import { toCashLine, type ApiLine } from "@/pages/finance/cash-flow/journalApi";
import { pairCandidates } from "@/pages/finance/cash-flow/journalPair";
import { catFilter, groupedCatOptions } from "@/pages/finance/cash-flow/journalSelection";

vi.mock("@/api/backendApi", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/api/backendApi")>()), backendRequest: vi.fn() }));

const api = (over: Partial<ApiLine> = {}): ApiLine => ({
  line_uid: "0123456789abcdef", account_key: "P", business_date: "2026-10-24", month: "2026-10", time: null, currency_code: "USD",
  amount: "-10000.0000", amount_cny: null, balance_after: null, description: "", memo: "", counterparty_name: "", counterparty_account_last4: "",
  source_ref: "", file_row_order: 1, category_code: "T02", category_source: "规则", pair_id: null, flags: [], refs: [],
  exclude_amount: null, exclude_reason: null, list_excluded_cny: "0", stage: "todo", stage_reason: null, review_note: null, version: 0, ...over,
});

describe("round 3 fields", () => {
  it("reads fee parts, manual pair and auto-exclude reason", () => {
    const line = toCashLine(api({
      parts: [{ amount: "9986.8000", category_code: "T02" }, { amount: "13.2000", category_code: "F01", fee_layer: "fee" }],
      manual_pair: "M1", auto_exclude_reason: "已在主账号记录",
    }));
    expect(line.parts).toEqual([{ amt: -9986.8, cat: "T02" }, { amt: -13.2, cat: "F01", fee: "fee" }]);
    expect(line.manualPair).toBe("M1");
    expect(line.autoExcludeReason).toBe("已在主账号记录");
  });
});

describe("category search", () => {
  const option = { value: "F01", label: "F01 财务费用·手续费" };
  it("matches code, words in any order and characters in order", () => {
    expect(catFilter("f01", option)).toBe(true);
    expect(catFilter("手续费 财务", option)).toBe(true);
    expect(catFilter("手费", option)).toBe(true);
    expect(catFilter("工资", option)).toBe(false);
  });
  it("groups by big category and leaves out X01 unless asked", () => {
    const cats = [{ code: "F01", big: "财务费用", name: "手续费" }, { code: "X01", big: "剔除", name: "非本公司" }];
    expect(groupedCatOptions(cats).map((group) => group.label)).toEqual(["财务费用"]);
    expect(groupedCatOptions(cats, true).map((group) => group.label)).toEqual(["财务费用", "剔除"]);
  });
});

describe("pairCandidates", () => {
  it("lists opposite, unpaired lines of other accounts within 15 days, closest amount first", () => {
    const out = toCashLine(api());
    const near = toCashLine(api({ line_uid: "aaaaaaaaaaaaaaaa", account_key: "B", business_date: "2026-10-26", amount: "9986.8000" }));
    const far = toCashLine(api({ line_uid: "bbbbbbbbbbbbbbbb", account_key: "C", business_date: "2026-10-25", amount: "100.0000" }));
    const sameAccount = toCashLine(api({ line_uid: "cccccccccccccccc", amount: "10000.0000" }));
    const paired = toCashLine(api({ line_uid: "dddddddddddddddd", account_key: "B", amount: "10000.0000", pair_id: "P1" }));
    const late = toCashLine(api({ line_uid: "eeeeeeeeeeeeeeee", account_key: "B", business_date: "2026-11-20", amount: "10000.0000" }));
    expect(pairCandidates(out, [out, far, near, sameAccount, paired, late]).map((item) => item.line.id)).toEqual([near.id, far.id]);
  });
  it("searches all dates by account, amount, summary and counterparty when a keyword is given", () => {
    const out = toCashLine(api());
    const old = toCashLine(api({ line_uid: "ffffffffffffffff", account_key: "B", business_date: "2026-08-01", amount: "9986.8000", description: "汇入 BANK OF CHINA", counterparty_name: "甲公司" }));
    const near = toCashLine(api({ line_uid: "aaaaaaaaaaaaaaaa", account_key: "C", business_date: "2026-10-25", amount: "100.0000" }));
    const name = (acct: string) => (acct === "B" ? "中行美元户" : acct);
    expect(pairCandidates(out, [out, old, near]).map((item) => item.line.id)).toEqual([near.id]);
    expect(pairCandidates(out, [out, old, near], "9,986.80", name).map((item) => item.line.id)).toEqual([old.id]);
    expect(pairCandidates(out, [out, old, near], "中行 甲公司", name).map((item) => item.line.id)).toEqual([old.id]);
    expect(pairCandidates(out, [out, old, near], "bank of", name).map((item) => item.line.id)).toEqual([old.id]);
    expect(pairCandidates(out, [out, old, near], "没有这个", name)).toEqual([]);
  });
});

describe("split rows", () => {
  it("adds child rows, finds parents by part category and writes the split into the memo", async () => {
    const { lineHasCat, splitSummary, withPartRows, isPartRow } = await import("@/pages/finance/cash-flow/journalParts");
    const line = toCashLine(api({ parts: [{ amount: "9986.8000", category_code: null }, { amount: "13.2000", category_code: "F01", fee_layer: "fee" }] }));
    const [row] = withPartRows([line]);
    expect(row.children?.map((child) => [child.id, child.amt, child.cat, child.fee, isPartRow(child)])).toEqual([
      [`${line.id}#p1`, -9986.8, "", undefined, true],
      [`${line.id}#p2`, -13.2, "F01", "fee", true],
    ]);
    expect(lineHasCat(line, "F01")).toBe(true);
    expect(lineHasCat(line, "G03")).toBe(false);
    expect(splitSummary(line)).toBe("拆分 2 行：-9,986.80 待分类 / -13.20 手续费 F01");
  });

  it("child rows keep the account and party, inherit the summary until they get their own", async () => {
    const { withPartRows } = await import("@/pages/finance/cash-flow/journalParts");
    const line = toCashLine(api({ parts: [{ amount: "9986.8000", category_code: null }, { amount: "13.2000", category_code: "F01", fee_layer: "fee", description: "到账手续费", memo: "中行扣" }] }));
    const children = withPartRows([line])[0].children ?? [];
    expect(children.map((child) => [child.acct, child.party, child.sum, child.ownSum, child.memo])).toEqual([
      [line.acct, line.party, line.sum, false, ""],
      [line.acct, line.party, "到账手续费", true, "中行扣"],
    ]);
  });

  it("child rows split the parent's RMB by amount, rounding difference on the last row", async () => {
    const { partCny, withPartRows } = await import("@/pages/finance/cash-flow/journalParts");
    const line = { ...toCashLine(api({ parts: [{ amount: "40.0000", category_code: "G08" }, { amount: "60.0000", category_code: "G02" }] })), cur: "USD", amt: -100, cny: -667.51 };
    const cnys = partCny(line);
    expect(cnys).toEqual([-267, -400.51]);
    expect(withPartRows([line])[0].children?.map((child) => child.cny)).toEqual(cnys);
    expect(partCny({ ...line, cny: null })).toEqual([null, null]);
  });
});

describe("split by RMB", () => {
  it("converts RMB rows back to the original currency at the line's own rate, rest on the last row", async () => {
    const { cnyToOriginal } = await import("@/pages/finance/cash-flow/journalParts");
    // 合成数据：付 $100.00，到账 ¥667.50（汇率 6.675），两张单 ¥100.00 + ¥567.50
    expect(cnyToOriginal([100, 567.5], 100, 667.5)).toEqual([14.98, 85.02]);
    const rows = cnyToOriginal([100, 100, 467.5], 100, 667.5);
    expect(Math.round(rows.reduce((sum, value) => sum + value, 0) * 100) / 100).toBe(100);
    expect(cnyToOriginal([], 1, 1)).toEqual([]);
  });
});
