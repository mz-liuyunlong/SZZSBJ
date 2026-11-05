/**
 * 日记账：勾选列、批量操作（初审通过 / 终审 / 改类别 / 剔除 / 配对）、导出 Excel。
 * rocky 11-05：初审只有通过（点错了在详情里撤销）；批量剔除填一次原因写到每一笔；勾两笔可以配对。
 * 后端没有批量接口：批量 = 对勾选的每一笔逐笔调用流水事件接口，每笔带自己的版本号，失败的单独列出来，不影响其他笔。
 * 导出在浏览器里生成：有勾选导出勾选的，没勾选导出当前筛选下的全部流水（日记账已经一次读全了，不分页）。
 */
import { DownOutlined } from "@ant-design/icons";
import { Button, Dropdown, Input, Modal, Select, Tooltip, Typography, message } from "antd";
import { useMemo, useState } from "react";
import * as XLSX from "xlsx";
import { asLive, cashErrorText, postLineEvent, type LineEventKind, type LiveCashLine } from "@/pages/finance/cash-flow/journalApi";
import { pairLines } from "@/pages/finance/cash-flow/journalPair";
import { catFilter, groupedCatOptions } from "@/pages/finance/cash-flow/journalSelection";
import { isExcluded, isFirstPending, PREVIEW_ACTION_TIP, REVIEW_TAG, type ReviewMark } from "@/pages/finance/cash-flow/journalShared";
import type { CashLine, CashSnapshot } from "@/pages/finance/localFinData";
import { currencyName } from "@/pages/finance/currencyName";

type BatchKind = "pass1" | "pass2" | "reject2" | "category" | "exclude" | "pair";
interface BatchDef { label: string; event: LineEventKind; reason: boolean; danger?: boolean; liveOnly?: boolean; done: string; skipText: string }
const BATCH: Record<BatchKind, BatchDef> = {
  pass1: { label: "批量初审通过", event: "review1_pass", reason: false, done: "初审通过", skipText: "不在待初审" },
  pass2: { label: "批量终审通过", event: "review2_pass", reason: false, done: "终审通过", skipText: "不在待终审" },
  reject2: { label: "批量终审驳回", event: "review2_reject", reason: true, danger: true, done: "终审驳回到待初审", skipText: "不在待终审" },
  category: { label: "批量改类别", event: "set_category", reason: false, liveOnly: true, done: "已改类别", skipText: "已剔除 / 已拆分 / 已经是这个类别" },
  exclude: { label: "批量剔除", event: "exclude", reason: true, danger: true, liveOnly: true, done: "已剔除", skipText: "已经剔除了 / 已拆分" },
  pair: { label: "配对（勾两笔）", event: "pair", reason: false, liveOnly: true, done: "已配对", skipText: "已配对 / 已终审" },
};

const liveOf = (lines: CashLine[]) => lines.flatMap((line) => { const target = asLive(line); return target ? [target] : []; });
/** 勾选配对：正好两笔、不同账户、一出一进。 */
const pairable = (lines: LiveCashLine[]) => lines.length === 2 && lines[0].acct !== lines[1].acct && (lines[0].amt ?? 0) * (lines[1].amt ?? 0) < 0;
function pairHint(lines: CashLine[]) {
  if (lines.length !== 2) return `配对要正好勾两笔（能配的有 ${lines.length} 笔）。`;
  const [a, b] = lines;
  if (a.acct === b.acct) return "两笔在同一个账户，不能配对。";
  if ((a.amt ?? 0) * (b.amt ?? 0) >= 0) return "要一笔付出、一笔收到才能配对。";
  const gap = a.cur === b.cur ? Math.abs(Math.abs(a.amt ?? 0) - Math.abs(b.amt ?? 0)) : null;
  return `把这两笔认成同一笔内部转账（不改金额和类别，不退回审核）。${gap ? `两边差 ${gap.toFixed(2)}，配上后在异常里显示差额，可以确认记为手续费。` : ""}配错了在详情里点「取消配对」。`;
}

interface Props {
  live: boolean;
  data: CashSnapshot;
  /** 当前筛选下的全部流水（导出用） */
  rows: CashLine[];
  /** 勾选的流水（只算当前筛选里看得到的） */
  selected: CashLine[];
  reviewOf: (line: CashLine) => ReviewMark;
  /** 初审要不要先写差额说明（审批单金额 ≠ 流水金额）；要写的批量初审通过时跳过，逐笔处理 */
  needsNote: (line: CashLine) => boolean;
  alertsText: (line: CashLine) => string;
  /** 本地预览：审核只记在本页 */
  onLocalReview: (marks: Record<string, ReviewMark>) => void;
  /** 批量做完：清空勾选、重读 */
  onDone: () => void;
}

export function JournalBatchActions({ live, data, rows, selected, reviewOf, needsNote, alertsText, onLocalReview, onDone }: Props) {
  const [messageApi, holder] = message.useMessage();
  const [modal, modalHolder] = Modal.useModal();
  const [pending, setPending] = useState<BatchKind>();
  const [reason, setReason] = useState("");
  const [running, setRunning] = useState(false);
  const [category, setCategory] = useState<string>();
  /* 类别下拉：按大类分组，可以输入代码或名称搜索；X01 不能选，剔除要逐笔写原因。 */
  const categoryOptions = useMemo(() => groupedCatOptions(data.cats), [data.cats]);

  /* 每类批量动作：哪些能做、哪些跳过（跳过的原因）。 */
  const plan = (kind: BatchKind) => {
    const todo: CashLine[] = [];
    let wrongStage = 0;
    let noteNeeded = 0;
    let reviewed = 0;
    for (const line of selected) {
      const stage = reviewOf(line).stage;
      if (kind === "exclude") {
        if (isExcluded(line) || line.parts) { wrongStage += 1; continue; }
        if (stage === "ok1" || stage === "ok2") reviewed += 1;
        todo.push(line);
        continue;
      }
      if (kind === "pair") {
        if (line.pair || stage === "ok2") { wrongStage += 1; continue; }
        todo.push(line);
        continue;
      }
      if (kind === "category") {
        if (isExcluded(line) || line.parts || (category != null && line.cat === category)) { wrongStage += 1; continue; }
        if (stage === "ok1" || stage === "ok2") reviewed += 1;
        todo.push(line);
        continue;
      }
      const ok = kind === "pass1" ? isFirstPending(stage) : stage === "ok1";
      if (!ok) { wrongStage += 1; continue; }
      if (kind === "pass1" && needsNote(line)) { noteNeeded += 1; continue; }
      todo.push(line);
    }
    return { todo, wrongStage, noteNeeded, reviewed };
  };
  const current = pending ? plan(pending) : undefined;
  const close = () => { setPending(undefined); setReason(""); setCategory(undefined); };

  const run = async () => {
    if (!pending || !current || !current.todo.length) return;
    const def = BATCH[pending];
    const text = reason.trim();
    if (def.reason && !text) return;
    if (pending === "category" && !category) return;
    if (pending === "pair") {
      const lines = liveOf(current.todo);
      if (!pairable(lines)) return;
      setRunning(true);
      const failed = await pairLines(lines, "pair");
      setRunning(false);
      close();
      onDone();
      if (failed.length) void messageApi.error(failed.join("；"));
      else void messageApi.success("已配对，两边金额有差的会在异常里显示差额");
      return;
    }
    if (!live && pending !== "category") {
      const stage = pending === "pass1" ? "ok1" : pending === "pass2" ? "ok2" : "rej2";
      onLocalReview(Object.fromEntries(current.todo.map((line) => [line.id, { ...reviewOf(line), stage, reason: def.reason ? text : undefined }])));
      void messageApi.success(`${def.done} ${current.todo.length} 笔（${PREVIEW_ACTION_TIP}）`);
      close();
      onDone();
      return;
    }
    setRunning(true);
    const failed: { line: CashLine; why: string }[] = [];
    let ok = 0;
    let autoReset = 0;
    const key = "journal-batch";
    for (const [index, line] of current.todo.entries()) {
      void messageApi.open({ key, type: "loading", content: `${def.label}：${index + 1} / ${current.todo.length}`, duration: 0 });
      const target = asLive(line);
      if (!target) { failed.push({ line, why: "不是接口数据" }); continue; }
      try {
        const result = await postLineEvent(target, def.event, pending === "category" ? { payload: { category_code: category } } : def.reason ? { reason: text } : {});
        ok += 1;
        if (result.auto_reset) autoReset += 1;
      } catch (error) {
        failed.push({ line, why: cashErrorText(error) });
      }
    }
    messageApi.destroy(key);
    setRunning(false);
    close();
    onDone();
    const skipped = current.wrongStage + current.noteNeeded;
    const tail = `${skipped ? `，跳过 ${skipped} 笔` : ""}${autoReset ? `；其中 ${autoReset} 笔已审过，自动退回待初审` : ""}`;
    if (!failed.length) { void messageApi.success(`${def.done} ${ok} 笔${tail}`); return; }
    modal.warning({
      title: `${def.label}：成功 ${ok} 笔，失败 ${failed.length} 笔${skipped ? `，跳过 ${skipped} 笔` : ""}`,
      width: 560,
      content: (
        <ul>
          {failed.slice(0, 20).map(({ line, why }) => <li key={line.id}>{line.date} · {line.id.split(":").pop()} · {why}</li>)}
          {failed.length > 20 && <li>……另有 {failed.length - 20} 笔</li>}
        </ul>
      ),
    });
  };

  const exportExcel = () => {
    const source = selected.length ? selected : rows;
    if (!source.length) { void messageApi.info("当前筛选下没有流水"); return; }
    const accountName = new Map(data.accounts.map((item) => [item.id, item.name]));
    const catName = new Map(data.cats.map((cat) => [cat.code, `${cat.code} ${cat.big}·${cat.name}`]));
    const hide = (line: CashLine, value: string | number | null | undefined) => (line.masked ? "****" : value ?? "");
    const header = ["日期", "时间", "流水 id", "账户", "币种", "金额", "折人民币", "余额", "摘要", "备注", "对方", "类别", "类别来源", "审批单", "异常", "审核状态", "不通过原因", "差额说明", "剔除"];
    const body = source.map((line) => {
      const mark = reviewOf(line);
      return [line.date, line.time ?? "", line.id, accountName.get(line.acct) ?? line.acct, currencyName(line.cur), hide(line, line.amt), line.cur === "CNY" ? "" : hide(line, line.cny), hide(line, line.bal),
        hide(line, line.sum), hide(line, line.memo !== line.sum ? line.memo : ""), line.party ?? "", line.parts ? `拆分 ${line.parts.length} 行` : catName.get(line.cat) ?? line.cat ?? "", line.cat_src ?? "",
        line.refs.join(" "), alertsText(line), REVIEW_TAG[mark.stage].text, mark.reason ?? "", mark.note ?? "", isExcluded(line) ? "是" : ""];
    });
    const sheet = XLSX.utils.aoa_to_sheet([header, ...body]);
    sheet["!cols"] = header.map((title) => ({ wch: ["摘要", "备注", "对方", "类别", "账户"].includes(title) ? 24 : title === "流水 id" ? 30 : 12 }));
    const book = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(book, sheet, "日记账");
    const now = new Date();
    const pad = (value: number) => String(value).padStart(2, "0");
    XLSX.writeFile(book, `日记账_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}_${source.length}笔.xlsx`);
    void messageApi.success(`已导出 ${source.length} 笔${selected.length ? "（勾选的）" : "（当前筛选）"}`);
  };

  const items = (Object.keys(BATCH) as BatchKind[]).map((kind) => {
    const locked = BATCH[kind].liveOnly && !live;
    return { key: kind, danger: BATCH[kind].danger, disabled: locked, label: locked ? <Tooltip title="本地预览不能改类别">{BATCH[kind].label}</Tooltip> : BATCH[kind].label };
  });
  const def = pending ? BATCH[pending] : undefined;

  return (
    <>
      {holder}
      {modalHolder}
      <Tooltip title={selected.length ? "" : "先在表格最左边勾选流水"}>
        <Dropdown disabled={!selected.length || running} trigger={["click"]} menu={{ items, onClick: ({ key }) => setPending(key as BatchKind) }}>
          <Button loading={running}>批量操作{selected.length ? `（${selected.length}）` : ""} <DownOutlined aria-hidden="true" /></Button>
        </Dropdown>
      </Tooltip>
      <Tooltip title={selected.length ? `导出勾选的 ${selected.length} 笔` : `导出当前筛选下的 ${rows.length} 笔`}>
        <Button onClick={exportExcel} disabled={running}>导出 Excel</Button>
      </Tooltip>
      <Modal open={Boolean(pending)} title={def?.label} okText={`确定（${current?.todo.length ?? 0} 笔）`} cancelText="取消" confirmLoading={running}
        okButtonProps={{ danger: def?.danger, disabled: !current?.todo.length || (def?.reason && !reason.trim()) || (pending === "category" && !category) || (pending === "pair" && current && !pairable(liveOf(current.todo))) }} onOk={() => void run()} onCancel={() => !running && close()} destroyOnHidden>
        {current && def && <>
          <Typography.Paragraph>勾选 {selected.length} 笔，这次处理 <Typography.Text strong>{current.todo.length}</Typography.Text> 笔。</Typography.Paragraph>
          {current.wrongStage > 0 && <Typography.Paragraph type="secondary">跳过 {current.wrongStage} 笔：{def.skipText}。</Typography.Paragraph>}
          {current.noteNeeded > 0 && <Typography.Paragraph type="warning">跳过 {current.noteNeeded} 笔：审批单金额和流水金额对不上，要逐笔点 ✓ 写差额说明。</Typography.Paragraph>}
          {pending === "category" && <Select showSearch autoFocus style={{ width: "100%" }} placeholder="选类别（可输入代码或名称模糊搜索）" value={category} onChange={setCategory} options={categoryOptions}
            filterOption={catFilter} />}
          {(pending === "category" || pending === "exclude") && current.reviewed > 0 && <Typography.Paragraph type="warning" style={{ marginTop: 8 }}>其中 {current.reviewed} 笔已经审过，改类别后会自动退回待初审。</Typography.Paragraph>}
          {pending === "reject2" && <Typography.Paragraph type="secondary">驳回后回到待初审。</Typography.Paragraph>}
          {pending === "exclude" && <Typography.Paragraph type="secondary">整笔剔除（记 X01，不算本公司收支）；要剔一部分的请逐笔在详情里剔除。可以逐笔撤销剔除。</Typography.Paragraph>}
          {pending === "pair" && <Typography.Paragraph type={pairable(liveOf(current.todo)) ? "secondary" : "danger"}>{pairHint(current.todo)}</Typography.Paragraph>}
          {def.reason && <Input.TextArea autoFocus rows={3} maxLength={200} showCount placeholder="必填：原因（同一条原因写到每一笔上）" value={reason} onChange={(event) => setReason(event.target.value)} />}
        </>}
      </Modal>
    </>
  );
}
