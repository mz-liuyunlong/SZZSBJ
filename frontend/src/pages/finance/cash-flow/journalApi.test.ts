import { describe, expect, it } from "vitest";
import { buildLiveSnapshot, cashErrorText, nextImportNode, resolveCashSource, type ApiAccount, type ApiAnomaly, type ApiCategory, type ApiLine } from "@/pages/finance/cash-flow/journalApi";
import { BackendRequestError } from "@/api/backendApi";

const line = (over: Partial<ApiLine> = {}): ApiLine => ({
  line_uid: "0123456789abcdef", account_key: "A1", business_date: "2026-10-10", month: "2026-10", time: "10:00:00", currency_code: "USD",
  amount: "-12.5000", amount_cny: null, balance_after: "100.0000", description: "摘要", memo: "", counterparty_name: "对方", counterparty_account_last4: "1234",
  source_ref: "R1", file_row_order: 3, category_code: null, category_source: "", pair_id: null, flags: [], refs: [],
  exclude_amount: null, exclude_reason: null, list_excluded_cny: "0", stage: "todo", stage_reason: null, review_note: null, version: 2, ...over,
});
const account: ApiAccount = { account_key: "A1", display_name: "假账户", entity: "甲", currency_code: "USD", kind: "平台", provider: "boc", account_no_last4: "0011", is_active: true, line_count: 1, last_file_name: "a.xlsx", cover_from: "2026-10-01", cover_to: "2026-10-31", cover_source: "表头" };
const category: ApiCategory = { code: "T02", big: "往来与资金", name: "内部调拨", is_internal: true, is_exclude: false };

describe("resolveCashSource", () => {
  it("defaults to demo in development and api in production, and honours the variable", () => {
    expect(resolveCashSource(undefined, true)).toBe("demo");
    expect(resolveCashSource(undefined, false)).toBe("api");
    expect(resolveCashSource("api", true)).toBe("api");
    expect(resolveCashSource("demo", false)).toBe("demo");
    expect(resolveCashSource("other", false)).toBe("api");
  });
});

describe("buildLiveSnapshot", () => {
  it("maps lines to the page shape, keeping empty cny as null", () => {
    const data = buildLiveSnapshot([account], [category], [line()], []);
    const [row] = data.lines;
    expect(row.id).toBe("A1:2026-10-10:abcdef");
    expect(row.amt).toBe(-12.5);
    expect(row.cny).toBeNull();
    expect(row.cat).toBe("");
    expect(row.excl).toBeUndefined();
    expect(data.accounts[0].stmt).toBe("尾号 0011");
    expect(data.meta.start).toBe("2026-10");
    expect(data.feishu).toEqual([]);
  });

  it("marks excluded lines from either manual amount or the exclusion list", () => {
    const data = buildLiveSnapshot([account], [category], [line({ exclude_amount: "1.0000" }), line({ line_uid: "1123456789abcdef", list_excluded_cny: "5.0000" })], []);
    expect(data.lines.map((row) => row.excl)).toEqual([1, 5]);
  });

  it("links anomalies to the page line id and leaves orphans unlinked", () => {
    const anomalies: ApiAnomaly[] = [
      { type: "内部转账未配对", account_key: "A1", date: "2026-10-10", message: "m", amount: "-12.5000", line_uid: "0123456789abcdef" },
      { type: "剔除未命中", account_key: "", date: "", message: "第 1 条", amount: "5.0000", line_uid: null },
    ];
    const data = buildLiveSnapshot([account], [category], [line()], anomalies);
    expect((data.anomalies[0] as unknown as { line: string }).line).toBe("A1:2026-10-10:abcdef");
    expect("line" in data.anomalies[1]).toBe(false);
  });
});

describe("nextImportNode", () => {
  it("is the coming Tuesday 15:00, and rolls over after Tuesday 15:00", () => {
    expect(nextImportNode(new Date(2026, 10, 4, 9))).toBe("2026-11-10 15:00");
    expect(nextImportNode(new Date(2026, 10, 10, 9))).toBe("2026-11-10 15:00");
    expect(nextImportNode(new Date(2026, 10, 10, 16))).toBe("2026-11-17 15:00");
  });
});

describe("cashErrorText", () => {
  it("explains status codes", () => {
    expect(cashErrorText(new BackendRequestError(403, "FORBIDDEN"))).toBe("只有超级管理员能操作");
    expect(cashErrorText(new BackendRequestError(413, "X"))).toBe("文件超过 20MB");
    expect(cashErrorText(new Error("x"))).toBe("操作失败，请稍后重试");
  });
});
