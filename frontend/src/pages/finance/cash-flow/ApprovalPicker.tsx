/**
 * 挂审批单的选择框（Rocky 11-10：只能手输 12 位单号不好用，要能搜、能选、选之前能先看审批单）。
 * 输入单号 / 收款人 / 金额 / 事由里的字都能搜；候选单（金额、日期对得上的）排在最前面；
 * 每个选项右边有「看」，点了打开审批单详情，不会挂上。也可以直接输入 12 位单号回车。
 */
import { AutoComplete, Typography } from "antd";
import { useMemo, useState } from "react";
import { maskCards } from "@/pages/finance/cash-flow/cardMask";
import { fmtMoney, type FeishuApproval } from "@/pages/finance/localFinData";

const SERIAL = /^\d{12}$/;
const MAX_OPTIONS = 50;

function matches(item: FeishuApproval, keyword: string) {
  const text = `${item.serial} ${item.payee} ${item.reason} ${item.kind} ${item.amount ?? ""} ${item.applicant}`.toLowerCase();
  return keyword.toLowerCase().split(/\s+/).filter(Boolean).every((word) => text.includes(word));
}

function ApprovalPicker({ approvals, candidates = [], onPick, onPreview, width = 200, placeholder = "搜单号 / 收款人 / 金额，或输 12 位单号回车" }: {
  approvals: FeishuApproval[];
  /** 金额、日期对得上的候选单号，排在最前面 */
  candidates?: string[];
  onPick: (serial: string) => Promise<boolean>;
  onPreview: (item: FeishuApproval) => void;
  width?: number;
  placeholder?: string;
}) {
  const [keyword, setKeyword] = useState("");
  const [busy, setBusy] = useState(false);
  const options = useMemo(() => {
    const first = new Set(candidates);
    const rows = approvals.filter((item) => !keyword.trim() || matches(item, keyword.trim()))
      .sort((a, b) => Number(first.has(b.serial)) - Number(first.has(a.serial)) || b.serial.localeCompare(a.serial))
      .slice(0, MAX_OPTIONS);
    return rows.map((item) => ({
      value: item.serial,
      label: (
        <span className="fin-cash-flow__picker-option">
          <span className="fin-cash-flow__picker-text">
            {first.has(item.serial) && <Typography.Text type="warning">候选 </Typography.Text>}
            {item.serial} · {item.masked ? "****" : fmtMoney(item.amount, item.cur)} · {(item.payee || "—").slice(0, 10)} · {maskCards(item.masked ? "" : item.reason || "").slice(0, 16)}
          </span>
          <Typography.Link className="fin-cash-flow__picker-view" onMouseDown={(event) => { event.preventDefault(); event.stopPropagation(); }}
            onClick={(event) => { event.preventDefault(); event.stopPropagation(); onPreview(item); }}>看</Typography.Link>
        </span>
      ),
    }));
  }, [approvals, candidates, keyword, onPreview]);
  const pick = async (serial: string) => {
    if (!SERIAL.test(serial) || busy) return;
    setBusy(true);
    try {
      if (await onPick(serial)) setKeyword("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <AutoComplete size="small" style={{ width }} popupMatchSelectWidth={440} value={keyword} options={options} disabled={busy} placeholder={placeholder}
      onSearch={setKeyword} onChange={(value: string) => setKeyword(value)} onSelect={(value: string) => void pick(value)}
      onKeyDown={(event) => { if (event.key === "Enter" && SERIAL.test(keyword.trim()) && !options.some((option) => option.value === keyword.trim())) void pick(keyword.trim()); }}
      notFoundContent={keyword.trim() ? "没有对得上的未付审批单；确定单号的话直接输 12 位回车" : null} />
  );
}

export default ApprovalPicker;
