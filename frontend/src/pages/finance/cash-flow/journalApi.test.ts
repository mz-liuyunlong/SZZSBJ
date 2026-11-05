import { describe, expect, it, vi } from "vitest";
import { buildLiveSnapshot, syncErrorText, syncFailedText, toFsDetail, type ApiApproval, cashErrorText, cashViewSource, fxNote, nextImportNode, postLineEvent, resolveCashSource, toCashLine, type ApiAccount, type ApiAnomaly, type ApiCategory, type ApiLine } from "@/pages/finance/cash-flow/journalApi";
import { backendRequest, BackendRequestError } from "@/api/backendApi";

vi.mock("@/api/backendApi", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/api/backendApi")>()), backendRequest: vi.fn() }));

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

describe("cashViewSource", () => {
  it("shows building in production for every view except the live journal", () => {
    expect(cashViewSource("journal", false, true)).toBe("live");
    expect(cashViewSource("journal", true, true)).toBe("live");
    expect(cashViewSource("accounts", false, true)).toBe("building");
    expect(cashViewSource("stock", false, true)).toBe("building");
    expect(cashViewSource("journal", false, false)).toBe("building");
    expect(cashViewSource("accounts", true, true)).toBe("demo");
    expect(cashViewSource("journal", true, false)).toBe("demo");
  });
});

describe("postLineEvent", () => {
  it("sends kind, payload and reason as given, with the line's version as expected_version", async () => {
    vi.mocked(backendRequest).mockResolvedValue({ data: { stage: "ok1", version: 8, auto_reset: false } } as never);
    const target = toCashLine(line({ version: 7 }));
    const result = await postLineEvent(target, "attach_ref", { payload: { ref: "202610100001" }, reason: "补单" });
    expect(result).toEqual({ stage: "ok1", version: 8, auto_reset: false });
    const [url, init] = vi.mocked(backendRequest).mock.calls[0];
    expect(url).toBe("/api/finance/cashflow/lines/0123456789abcdef/events");
    expect(init?.method).toBe("POST");
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    expect(body.kind).toBe("attach_ref");
    expect(body.payload).toEqual({ ref: "202610100001" });
    expect(body.reason).toBe("补单");
    expect(body.expected_version).toBe(target.version);
    expect(body.expected_version).toBe(7);
    expect(typeof body.idempotency_key).toBe("string");
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
    expect(row.excl).toBe(false);
    expect(data.accounts[0].stmt).toBe("尾号 0011");
    expect(data.meta.start).toBe("2026-10");
    expect(data.feishu).toEqual([]);
  });

  it("marks excluded lines from either manual amount or the exclusion list", () => {
    const data = buildLiveSnapshot([account], [category], [line({ exclude_amount: "1.0000" }), line({ line_uid: "1123456789abcdef", list_excluded_cny: "5.0000" })], []);
    expect(data.lines.map((row) => row.excl)).toEqual([true, true]);
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

const approval = (over: Partial<ApiApproval> = {}): ApiApproval => ({
  serial: "202610010001", kind: "付款申请", status: "APPROVED", status_text: "已同意", state: "已付", started_at: "2026-10-01 09:00", completed_at: "2026-10-02 10:00", handled_at: "2026-10-02 09:30", applicant: "申请人",
  reason: "合成事由", amount: "100.0000", currency_code: "CNY", amount_cny: "100.0000", pay_method: "转账", invoice: "是", payee: "收款人", bank: "测试银行", last4: "1234", fee_category: "", related_serial: "",
  items: [{ content: "明细", amount: "100", category: "" }], attachments: [{ source: "form", what: "附件", item: 0, is_image: false, title: "a.pdf" }], records: [], comments: [],
  paid: [{ line_uid: "0123456789abcdef", amount_cny: "100.0000" }], paid_sum: "100.0000", fetched_at: null, ...over,
});

describe("approvals in the live snapshot", () => {
  it("maps approvals and links paid lines by the page line id", () => {
    const snapshot = buildLiveSnapshot([account], [category], [line()], [], [approval()]);
    const item = snapshot.feishu[0];
    expect(item.status).toBe("已同意");
    expect(item.start).toBe("2026-10-01");
    expect(item.end).toBe("2026-10-02");
    expect(item.amount).toBe(100);
    expect(item.paid.map((row) => row.line)).toEqual([snapshot.lines[0].id]);
  });

  it("drops paid lines the page does not have", () => {
    const snapshot = buildLiveSnapshot([account], [category], [line()], [], [approval({ paid: [{ line_uid: "ffffffffffffffff", amount_cny: "1" }] })]);
    expect(snapshot.feishu[0].paid).toEqual([]);
  });

  it("keeps candidates on the live line", () => {
    expect(toCashLine(line({ approval_candidates: ["202610010001"] })).candidates).toEqual(["202610010001"]);
    expect(toCashLine(line()).candidates).toEqual([]);
    const edited = toCashLine(line({ amount: "-100.00", manual_description: "房租", manual_memo: null, parts: [{ amount: "60.0000", category_code: "G02" }, { amount: "40.0000", category_code: null }] }));
    expect([edited.sum, edited.origSum]).toEqual(["房租", line().description]);
    expect(edited.memo).toBe(line().memo);
    expect(edited.parts).toEqual([{ amt: -60, cat: "G02" }, { amt: -40, cat: "" }]);
    expect(toCashLine(line()).parts).toBeUndefined();
  });

  it("marks attachments as metadata only so no link is built", () => {
    const detail = toFsDetail(approval());
    expect(detail.files[0].name).toBe("");
    expect(detail.files[0].title).toBe("a.pdf");
    expect(detail.handled).toBe("2026-10-02 09:30");
  });
});

describe("sync messages", () => {
  it("explains configuration and queue problems", () => {
    expect(syncErrorText(new BackendRequestError(409, "x", "r"))).toContain("还没配置");
    expect(syncErrorText(new BackendRequestError(503, "x", "r"))).toContain("任务队列");
  });
  it("carries the provider code in the failure text", () => {
    expect(syncFailedText("FEISHU_APPROVAL_LIST_HTTP_400_CODE_1")).toContain("FEISHU_APPROVAL_LIST_HTTP_400_CODE_1");
    expect(syncFailedText(null)).toContain("同步失败");
  });
});

describe("fxNote", () => {
  it("labels Payoneer's own rate and the blank withdrawals waiting for the month-end statement", () => {
    expect(fxNote(toCashLine(line({ amount_cny: "-20000.0000", fx_rate: "6.6751", fx_source: "payoneer" })))).toBe("派安盈实际汇率 6.6751");
    expect(fxNote(toCashLine(line({ fx_source: "pending" })))).toBe("等派安盈月结单");
    expect(fxNote(toCashLine(line({ amount_cny: "-88.7500", fx_rate: "7.1", fx_source: "lingxing" })))).toBeUndefined();
    expect(fxNote(toCashLine(line()))).toBeUndefined();
  });
});
