/** 日记账；从 FinanceCashFlowPage.tsx 原样搬出。 */
import { CheckOutlined, CloseOutlined, SettingOutlined } from "@ant-design/icons";
import { Alert, AutoComplete, Button, Input, Modal, Select, Space, Tag, Tooltip, Typography, message } from "antd";
import { type ProColumns } from "@ant-design/pro-components";
import { useEffect, useMemo, useState } from "react";
import CommittedSearch from "@/components/report-table/CommittedSearch";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import ResetButton from "@/components/report-table/ResetButton";
import RuntimeColumnConfigDrawer from "@/components/report-table/RuntimeColumnConfigDrawer";
import FinanceBoardFrame, { FinMoney, LOCKED_TIP } from "@/pages/finance/FinanceBoardFrame";
import ImportDrawer from "@/pages/finance/cash-flow/ImportDrawer";
import { asLive, cashErrorText, postLineEvent, useRefreshJournal, type LineEventKind, type LiveCashLine } from "@/pages/finance/cash-flow/journalApi";
import { ALERT_GUIDE, alertShort, toCashAlerts, useApprovals, type CashAlert } from "@/pages/finance/cash-flow/data";
import { accountLabel, fmtMoney, type CashLine, type CashSnapshot, type FeishuApproval } from "@/pages/finance/localFinData";
import ReportFacetSelect from "@/shared/report-filters";
import { writeUserPreference } from "@/shared/preferences/userPreferenceCache";
import { type ReviewCard, STATE_COLOR, EMPTY, isOpenApproval, isUncat, mergeFeishu, noFlowAlerts, orphanInScope, isExcluded, type ReviewStage, type ReviewMark, REVIEW_TAG, baseReview, isFirstPending, REVIEW_STAGE_OPTIONS, PREVIEW_ACTION_TIP, viewOf, amountDiff, JOURNAL_COLUMN_PREF_KEY, JOURNAL_COLUMN_PREF_VERSION, JOURNAL_FIXED_KEYS, JOURNAL_DEFAULT_KEYS, JOURNAL_COLUMN_GROUPS, readJournalColumns, icon, HANDOFF_EVENT, readHandoff } from "@/pages/finance/cash-flow/journalShared";
import { ApprovalDrawer } from "@/pages/finance/cash-flow/ApprovalDrawer";
import { BoardTable } from "@/pages/finance/cash-flow/BoardTable";
import { LineDrawer } from "@/pages/finance/cash-flow/LineDrawer";

/* ======================================================= 日记账 */
export function JournalBoard({ data, live = false }: { data: CashSnapshot; live?: boolean }) {
  const refresh = useRefreshJournal();
  const handoff = useMemo(() => readHandoff(), []);
  const [accounts, setAccounts] = useState<string[]>(handoff.account ? [handoff.account] : []);
  const [month, setMonth] = useState<string>(handoff.month ?? "");
  const [cats, setCats] = useState<string[]>(handoff.cats ?? []);
  const [flow, setFlow] = useState<"" | "in" | "out">("");
  const [stages, setStages] = useState<ReviewStage[]>([]);
  const [alertTypes, setAlertTypes] = useState<string[]>(handoff.alerts ?? []);
  const [search, setSearch] = useState({ field: "text", keyword: "" });
  const [card, setCard] = useState<ReviewCard>(handoff.card ?? "all");
  useEffect(() => {
    const apply = () => {
      const next = readHandoff();
      if (!Object.keys(next).length) return;
      setAccounts(next.account ? [next.account] : []);
      setMonth(next.month ?? "");
      setCats(next.cats ?? []);
      setAlertTypes(next.alerts ?? []);
      setFlow("");
      setStages([]);
      setSearch({ field: "text", keyword: "" });
      setCard(next.card ?? "all");
    };
    window.addEventListener(HANDOFF_EVENT, apply);
    return () => window.removeEventListener(HANDOFF_EVENT, apply);
  }, []);
  const [lineOpen, setLineOpen] = useState<CashLine>();
  const [approvalOpen, setApprovalOpen] = useState<FeishuApproval>();
  const [reviews, setReviews] = useState<Record<string, ReviewMark>>({});
  const [rejecting, setRejecting] = useState<{ line: CashLine; level: 1 | 2 }>();
  const [rejectReason, setRejectReason] = useState("");
  const [noting, setNoting] = useState<CashLine>();
  const [noteText, setNoteText] = useState("");
  const [excluding, setExcluding] = useState<LiveCashLine>();
  const [excludeAmount, setExcludeAmount] = useState("");
  const [excludeReason, setExcludeReason] = useState("");
  const approvalsFile = useApprovals(!live);
  const details = useMemo(() => approvalsFile.data?.items ?? {}, [approvalsFile.data]);
  const [columnKeys, setColumnKeys] = useState<string[]>(readJournalColumns);
  const [columnConfigOpen, setColumnConfigOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [messageApi, messageHolder] = message.useMessage();
  const reviewOf = (line: CashLine) => reviews[line.id] ?? baseReview(line);
  /* 接口模式重读后，详情要用最新的那一行，否则带着旧版本号去写会被拒。 */
  const freshLine = lineOpen ? data.lines.find((line) => line.id === lineOpen.id) ?? lineOpen : undefined;
  /* 接口模式：写一条事件，成功或失败都重读（失败多半是别人刚改过）；返回是否写成功。 */
  const send = async (line: CashLine, kind: LineEventKind, fields: { payload?: Record<string, unknown>; reason?: string } = {}, done?: string): Promise<boolean> => {
    const target = asLive(line);
    if (!target) return false;
    let ok = false;
    try {
      const result = await postLineEvent(target, kind, fields);
      ok = true;
      if (done) void messageApi.success(done);
      if (result.auto_reset) void messageApi.info("这笔已审过，改动后自动退回待初审");
    } catch (error) {
      void messageApi.error(cashErrorText(error));
    }
    void refresh();
    return ok;
  };
  /* 初审：审批金额和流水金额有差额 → 必须先写差额说明（不限差额大小）；终审直接通过。 */
  const pass = (line: CashLine, level: 1 | 2, note?: string) => {
    const diff = amountDiff(line, approvalsOf(line));
    if (level === 1 && diff != null && diff !== 0 && note === undefined) {
      setNoteText(reviews[line.id]?.note ?? "");
      setNoting(line);
      return;
    }
    if (live) {
      void send(line, level === 1 ? "review1_pass" : "review2_pass", { payload: note ? { note } : {} }, `${level === 1 ? "初审" : "终审"}通过`);
      return;
    }
    setReviews((current) => ({ ...current, [line.id]: { stage: level === 1 ? "ok1" : "ok2", note: note ?? current[line.id]?.note } }));
    void messageApi.success(`${level === 1 ? "初审" : "终审"}通过（${PREVIEW_ACTION_TIP}）`);
  };
  const confirmNote = () => {
    if (!noting || !noteText.trim()) return;
    pass(noting, 1, noteText.trim());
    setNoting(undefined);
    setNoteText("");
  };
  const confirmReject = () => {
    if (!rejecting || !rejectReason.trim()) return;
    if (live) {
      void send(rejecting.line, rejecting.level === 1 ? "review1_reject" : "review2_reject", { reason: rejectReason.trim() }, rejecting.level === 1 ? "初审不通过，已记原因" : "终审不通过，已驳回到待初审");
      setRejecting(undefined);
      setRejectReason("");
      return;
    }
    setReviews((current) => ({ ...current, [rejecting.line.id]: { stage: rejecting.level === 1 ? "rej1" : "rej2", reason: rejectReason.trim(), note: current[rejecting.line.id]?.note } }));
    void messageApi.warning(rejecting.level === 1 ? "初审不通过，已记原因" : "终审不通过，已驳回到待初审");
    setRejecting(undefined);
    setRejectReason("");
  };
  const confirmExclude = () => {
    if (!excluding || !excludeReason.trim()) return;
    void send(excluding, "exclude", { reason: excludeReason.trim(), payload: excludeAmount.trim() ? { amount: excludeAmount.trim() } : {} }, "已剔除");
    setExcluding(undefined);
    setExcludeAmount("");
    setExcludeReason("");
  };
  const applyColumns = (keys: string[]) => {
    setColumnKeys(keys);
    writeUserPreference("anonymous", JOURNAL_COLUMN_PREF_KEY, JOURNAL_COLUMN_PREF_VERSION, keys);
    setColumnConfigOpen(false);
  };
  const feishuAll = useMemo(() => mergeFeishu(data, details), [data, details]);
  const approvals = useMemo(() => new Map(feishuAll.map((item) => [item.serial, item])), [feishuAll]);
  const approvalsOf = (line: CashLine) => line.refs.map((ref) => viewOf(ref, approvals.get(ref), details[ref]));
  const accountMap = useMemo(() => new Map(data.accounts.map((item) => [item.id, item])), [data]);
  /* 异常落到流水上：有流水号的直接挂；审批单类挂到关联了该单的流水；余额不连续按 账户 + 日期 + 余额 找断点那条流水。
     落不到流水上的进 orphans：要剔除的款没找到、审批单无付款流水、没关联流水的审批单金额不符；平时只计数，在「异常」筛选选中时才在表格上方列出。
     没关联流水的审批单未付 / 部分已付由「审批单无付款流水」统一代替，不重复列。 */
  const alertIndex = useMemo(() => {
    const byLine = new Map<string, CashAlert[]>();
    const orphans: CashAlert[] = [];
    orphans.push(...noFlowAlerts(data, feishuAll));
    const push = (id: string, item: CashAlert) => byLine.set(id, [...(byLine.get(id) ?? []), item]);
    for (const item of toCashAlerts(data.anomalies)) {
      if (item.line) { push(item.line, item); continue; }
      if (item.serial) {
        const hits = data.lines.filter((line) => line.refs.includes(item.serial as string));
        hits.forEach((line) => push(line.id, item));
        if (!hits.length && (!item.type.startsWith("审批单") || item.type === "审批单金额不符")) orphans.push(item);
        continue;
      }
      const hit = item.type === "余额不连续" ? data.lines.find((line) => line.acct === item.acct && line.date === item.date && line.bal != null && line.amt != null
        && Math.abs(line.bal - line.amt - (item.amt ?? NaN)) < 0.011) : undefined;
      if (hit) push(hit.id, { ...item, ref: hit.id, id: `${item.type}|${hit.id}` });
      else orphans.push(item);
    }
    return { byLine, orphans };
  }, [data, feishuAll]);
  const alertsOf = (line: CashLine) => alertIndex.byLine.get(line.id) ?? [];
  const realAlertsOf = (line: CashLine) => alertsOf(line).filter((item) => !item.hint);
  const realOrphans = alertIndex.orphans.filter((item) => !item.hint && orphanInScope(item, accounts, month));
  const alertTypeOptions = Array.from(new Set([...data.lines.flatMap((line) => realAlertsOf(line).map((item) => item.type)), ...realOrphans.map((item) => item.type)]))
    .map((value) => ({ value, label: alertShort(value), count: data.lines.filter((line) => realAlertsOf(line).some((item) => item.type === value)).length + realOrphans.filter((item) => item.type === value).length }));
  /* 找不到流水的异常（Rocky 11-04）：平时不展示，只算进「异常」卡数字；在「异常」筛选里选中这些类型时，才在表格上方列出来。 */
  const shownOrphans = realOrphans.filter((item) => alertTypes.includes(item.type));
  /* 「异常」卡：有异常的流水（已按全部筛选）+ 找不到流水的异常（按账户、月份；选了异常类型时也按类型）。 */
  const cardOrphans = alertTypes.length ? shownOrphans.length : realOrphans.length;
  const base = data.lines.filter((line) => (accounts.length === 0 || accounts.includes(line.acct)) && (!month || line.m === month)
    && (cats.length === 0 || cats.some((c) => (c === "NONE" ? isUncat(line) : line.cat === c)))
    && (!flow || (flow === "in" ? (line.amt ?? 0) > 0 : (line.amt ?? 0) < 0))
    && (stages.length === 0 || stages.includes(reviewOf(line).stage))
    && (alertTypes.length === 0 || realAlertsOf(line).some((item) => alertTypes.includes(item.type)))
    && (!search.keyword || (search.field === "party"
      ? (line.party ?? "").toLowerCase().includes(search.keyword.toLowerCase())
      : search.field === "ref"
        ? line.refs.some((ref) => ref.includes(search.keyword.trim()))
        : `${line.sum} ${line.memo} ${line.refs.join(" ")} ${line.id}`.toLowerCase().includes(search.keyword.toLowerCase()))));
  const counts: Record<ReviewCard, number> = {
    all: base.length,
    todo: base.filter((line) => isFirstPending(reviewOf(line).stage)).length,
    ok1: base.filter((line) => reviewOf(line).stage === "ok1").length,
    alert: base.filter((line) => realAlertsOf(line).length > 0).length,
    excluded: base.filter(isExcluded).length,
  };
  const rows = base.filter((line) => card === "all" || (card === "todo" ? isFirstPending(reviewOf(line).stage) : card === "ok1" ? reviewOf(line).stage === "ok1" : card === "alert" ? realAlertsOf(line).length > 0 : isExcluded(line)))
    .sort((a, b) => b.date.localeCompare(a.date) || (b.time ?? "").localeCompare(a.time ?? "") || (b.ord ?? 0) - (a.ord ?? 0));
  const cards: ManagementStatCardItem<ReviewCard>[] = [
    { key: "all", title: "全部流水", subtitle: "当前筛选", value: counts.all, tone: "normal", icon: icon("全") },
    { key: "todo", title: "待初审", subtitle: "含初审不通过 / 终审驳回", value: counts.todo, tone: counts.todo ? "warning" : "normal", icon: icon("初") },
    { key: "ok1", title: "待终审", subtitle: "初审已通过，等财务主管", value: counts.ok1, tone: "normal", icon: icon("终") },
    { key: "alert", title: "异常", subtitle: "有异常的流水 + 找不到流水的异常，都要处理", value: counts.alert + cardOrphans, tone: counts.alert + cardOrphans ? "danger" : "normal", icon: icon("!") },
    { key: "excluded", title: "已剔除", subtitle: "X01 非本公司", value: counts.excluded, tone: "normal", icon: icon("剔") },
  ];
  const catOptions = useMemo(() => data.cats.filter((cat) => !live || cat.code !== "X01").map((cat) => ({ value: cat.code, label: `${cat.code} ${cat.big}·${cat.name}` })), [data, live]);
  const openApprovalOptions = useMemo(() => feishuAll.filter((item) => isOpenApproval(item, data)).sort((a, b) => b.serial.localeCompare(a.serial))
    .map((item) => ({ value: item.serial, label: `${item.serial} ${item.masked ? "****" : fmtMoney(item.amount, item.cur)} ${(item.payee || "").slice(0, 10)} ${(item.masked ? "" : item.reason || "").slice(0, 16)}` })), [data, feishuAll]);
  const columnDefs: Record<string, ProColumns<CashLine>[]> = {
    date: [{ key: "date", title: "日期", dataIndex: "date", width: 116, fixed: "left", render: (_, row) => <span className="finance-board__stack">{row.date}<span className="finance-board__sub">{row.id.split(":").pop()}</span></span> }],
    acct: [{ key: "acct", title: "账户", dataIndex: "acct", width: 200, render: (_, row) => accountMap.get(row.acct)?.name ?? row.acct }],
    sum: [{ key: "sum", title: "摘要", dataIndex: "sum", width: 180, render: (_, row) => (row.masked ? <Typography.Text type="secondary">****</Typography.Text> : <Typography.Text ellipsis={{ tooltip: row.sum }} style={{ maxWidth: 164 }}>{row.sum || EMPTY}</Typography.Text>) }],
    memo: [{ key: "memo", title: "备注", dataIndex: "memo", width: 300, render: (_, row) => (row.masked ? <Typography.Text type="secondary">****</Typography.Text> : row.memo && row.memo !== row.sum ? <Typography.Text type="secondary" className="finance-board__fulltext">{row.memo}</Typography.Text> : EMPTY) }],
    party: [{ key: "party", title: "对方", dataIndex: "party", width: 200, render: (_, row) => (row.party ? <Typography.Text ellipsis={{ tooltip: row.party }} style={{ maxWidth: 184 }}>{row.party}</Typography.Text> : EMPTY) }],
    amt: [{ key: "amt", title: "金额", dataIndex: "amt", width: 130, align: "right", render: (_, row) => <FinMoney value={row.amt} cur={row.cur} masked={row.masked} /> }],
    cny: [{ key: "cny", title: "折人民币", dataIndex: "cny", width: 130, align: "right", render: (_, row) => (row.cur === "CNY" ? EMPTY : <FinMoney value={row.cny} masked={row.masked} />) }],
    bal: [{ key: "bal", title: "余额", dataIndex: "bal", width: 140, align: "right", render: (_, row) => <FinMoney value={row.bal ?? null} cur={row.cur} masked={row.masked} /> }],
    cat: [{ key: "cat", title: "类别", dataIndex: "cat", width: 230, tooltip: "直接在行上选类别；人工改过的优先于审批单与规则", render: (_, row) => (row.parts ? <Tag color="geekblue" bordered={false}>拆分 {row.parts.length} 行</Tag> : (
      <span className="finance-board__stack">
        <Tooltip title={live ? (row.cat === "X01" ? "已整笔剔除，要改类别先撤销剔除" : "") : LOCKED_TIP}><Select size="small" disabled={!live || row.cat === "X01"} style={{ width: 200 }} value={row.cat || undefined} placeholder={<Typography.Text type="danger">待分类</Typography.Text>} options={live && row.cat === "X01" ? data.cats.map((cat) => ({ value: cat.code, label: `${cat.code} ${cat.big}·${cat.name}` })) : catOptions} allowClear={live} onChange={(value?: string) => void send(row, "set_category", { payload: { category_code: value ?? null } })} /></Tooltip>
        <span className="finance-board__sub">来源：{row.cat_src || "—"}</span>
      </span>)) }],
    refs: [{ key: "refs", title: "审批单", dataIndex: "refs", width: 230, tooltip: "这笔付款对应哪张飞书审批单。自动：备注里有单号直接关联；金额 + 收款人 + 45 天内唯一候选自动关联。对不上的在这里输入或选未付审批单", render: (_, row) => (
      <span className="finance-board__stack">
        {row.refs.length > 0 && <Space size={4} wrap>{row.refs.map((ref) => { const item = approvals.get(ref); return <Tooltip key={ref} title={item ? `${item.kind} · ${item.state} · 点击看审批单` : "飞书里没找到"}><Tag bordered={false} className="finance-board__ref" color={item ? STATE_COLOR[item.state] ?? "blue" : "red"} closable={live} onClose={(event) => { event.preventDefault(); void send(row, "detach_ref", { payload: { ref } }); }} onClick={() => item && setApprovalOpen(item)}>{ref}</Tag></Tooltip>; })}</Space>}
        {live ? <Input size="small" style={{ width: 200 }} placeholder="输入 12 位审批单号，回车" onPressEnter={(event) => { const input = event.currentTarget; const ref = input.value.trim(); if (!/^\d{12}$/.test(ref)) { void messageApi.warning("审批单号是 12 位数字"); return; } void send(row, "attach_ref", { payload: { ref } }).then((ok) => { if (ok) input.value = ""; }); }} /> : <Tooltip title={LOCKED_TIP}><AutoComplete size="small" disabled style={{ width: 200 }} placeholder="关联审批单（输入或选未付单）" options={openApprovalOptions} /></Tooltip>}
      </span>) }],
    alert: [{ key: "alert", title: "异常", width: 150, tooltip: "这笔流水上待处理的异常（灰色是数据提示，不算异常）；点详情看说明和处理方法", render: (_, row) => {
      const list = alertsOf(row);
      return list.length ? <Space size={4} wrap>{list.map((item) => <Tooltip key={item.id} title={item.msg}><Tag bordered={false} color={item.hint ? undefined : "red"}>{item.hint ? item.type : alertShort(item.type)}</Tag></Tooltip>)}</Space> : EMPTY;
    } }],
    review: [
      { key: "review_state", title: "审核状态", width: 150, fixed: "right", tooltip: "审批流转：待初审 → 财务专员 ✓ → 待终审 → 财务主管 ✓ → 已终审（按钮变灰）。✗ 须填原因；终审 ✗ 驳回到待初审。审核后再改类别 / 关联审批单 / 拆分 / 剔除会自动退回待初审", render: (_, row) => { const mark = reviewOf(row); return (
        <span className="finance-board__stack">
          <Tag color={REVIEW_TAG[mark.stage].color} bordered={false}>{REVIEW_TAG[mark.stage].text}</Tag>
          {mark.reason && <Typography.Text type="danger" className="finance-board__fulltext finance-board__sub">原因：{mark.reason}</Typography.Text>}
        </span>); } },
      { key: "review_act", title: "审核", width: 84, fixed: "right", tooltip: "轮到初审时是初审、轮到终审时是终审（看左边审核状态）；✓ 通过，✗ 不通过须填原因；已终审变灰", render: (_, row) => { const stage = reviewOf(row).stage; const level: 1 | 2 | undefined = isFirstPending(stage) ? 1 : stage === "ok1" ? 2 : undefined; const name = level === 1 ? "初审" : "终审"; return (
        <span className="finance-board__review-row">
          <Tooltip title={level ? `${name}通过` : "已终审"}><Button size="small" type="text" className="finance-board__review-pass" aria-label={`${name}通过`} icon={<CheckOutlined aria-hidden="true" />} disabled={!level} onClick={() => level && pass(row, level)} /></Tooltip>
          <Tooltip title={level ? `${name}不通过（填原因${level === 2 ? "，驳回到待初审" : ""}）` : "已终审"}><Button size="small" type="text" danger aria-label={`${name}不通过`} icon={<CloseOutlined aria-hidden="true" />} disabled={!level} onClick={() => level && setRejecting({ line: row, level })} /></Tooltip>
        </span>); } },
    ],
  };
  const lineColumns: ProColumns<CashLine>[] = [
    ...columnDefs.date,
    ...columnKeys.filter((key) => !JOURNAL_FIXED_KEYS.includes(key)).flatMap((key) => columnDefs[key] ?? []),
    ...columnDefs.review,
    { key: "actions", title: "操作", width: 72, fixed: "right", render: (_, row) => <Space size={0}><Button type="link" size="small" onClick={() => setLineOpen(row)}>详情</Button></Space> },
  ];
  const months = data.meta.months;
  /* 按审批单号搜不到流水时，说明这张单的状态和在哪能看到。 */
  const refHint = (() => {
    const keyword = search.keyword.trim();
    if (!keyword || rows.length || !/^\d{6,}$/.test(keyword)) return "";
    const hits = feishuAll.filter((item) => item.serial.includes(keyword));
    if (!hits.length) return `没有流水，本地也没找到审批单 ${keyword}（可能还没从飞书同步过来）`;
    const item = hits[0];
    const where = item.status === "已同意" && (item.start || "") >= `${data.meta.start}-01` ? "飞书已同意，还没有付款流水；在「异常」筛选里选「审批单无付款流水」可以看到" : `飞书状态：${item.status || "—"}，付款状态：${item.state}`;
    return `审批单 ${item.serial}（${item.kind} ${item.masked ? "" : fmtMoney(item.amount, item.cur)} ${item.payee}）还没有关联任何流水，${where}${hits.length > 1 ? `；另有 ${hits.length - 1} 张单号相近` : ""}`;
  })();
  return (
    <FinanceBoardFrame
      title="日记账"
      preview={!live}
      subtitle="按银行明细顺序；流水 id 后 6 位是内容指纹，重复导入自动去重；类别来源：人工 > 审批单 > 规则"
      toolbar={<>
        <ReportFacetSelect mode="multiple" ariaLabel="账户" placeholder="账户" unit="个" value={accounts} options={data.accounts.map((item) => ({ value: item.id, label: accountLabel(item), count: data.lines.filter((line) => line.acct === item.id).length }))} onChange={(value) => setAccounts((value as string[] | undefined) ?? [])} />
        <ReportFacetSelect ariaLabel="月份" placeholder="全部月份" value={month || undefined} options={months.map((value) => ({ value, label: value }))} onChange={(value) => setMonth(value ? String(value) : "")} />
        <ReportFacetSelect ariaLabel="收入 / 支出" placeholder="收入 / 支出" triggerWidth={150} value={flow || undefined} options={[{ value: "in", label: "收入", count: data.lines.filter((line) => (line.amt ?? 0) > 0).length }, { value: "out", label: "支出", count: data.lines.filter((line) => (line.amt ?? 0) < 0).length }]} onChange={(value) => setFlow(value === "in" || value === "out" ? value : "")} />
        <ReportFacetSelect mode="multiple" ariaLabel="类别" placeholder="类别" unit="类" popupWidth={420} value={cats} options={[{ value: "NONE", label: "待分类", count: data.lines.filter(isUncat).length }, ...data.cats.map((cat) => ({ value: cat.code, label: `${cat.code} ${cat.big}·${cat.name}`, count: data.lines.filter((line) => line.cat === cat.code).length }))]} onChange={(value) => setCats((value as string[] | undefined) ?? [])} />
        <ReportFacetSelect mode="multiple" ariaLabel="审核状态" placeholder="审核状态" unit="项" value={stages} options={REVIEW_STAGE_OPTIONS.map((option) => ({ ...option, count: data.lines.filter((line) => reviewOf(line).stage === option.value).length }))} onChange={(value) => setStages((value as ReviewStage[] | undefined) ?? [])} />
        <ReportFacetSelect mode="multiple" ariaLabel="异常" placeholder="异常" unit="类" triggerWidth={150} value={alertTypes} options={alertTypeOptions} onChange={(value) => setAlertTypes((value as string[] | undefined) ?? [])} />
        <CommittedSearch className="finance-board__search fin-cash-flow__search" typeAriaLabel="搜索类型" typeOptions={[{ value: "text", label: "摘要备注" }, { value: "party", label: "收款人" }, { value: "ref", label: "审批单号" }]} typeValue={search.field} inputAriaLabel="搜索流水" inputPlaceholder="输入后回车" inputValue={search.keyword} onCommit={({ searchField, keyword }) => setSearch({ field: searchField, keyword })} />
        <ResetButton onClick={() => { setAccounts([]); setMonth(""); setFlow(""); setCats([]); setStages([]); setAlertTypes([]); setSearch({ field: "text", keyword: "" }); setCard("all"); }} />
        <Space className="finance-board__toolbar-actions" size={8}><Button type="primary" onClick={() => setImportOpen(true)}>流水导入</Button><Tooltip title={LOCKED_TIP}><Space><Button disabled>批量操作</Button><Button disabled>导出 Excel</Button></Space></Tooltip><Button aria-label="列配置" icon={<SettingOutlined aria-hidden="true" />} onClick={() => setColumnConfigOpen(true)} /></Space>
      </>}
      summary={<ManagementStatCards<ReviewCard> ariaLabel="日记账统计" className="finance-board__summary finance-board__summary--5" cards={cards} activeKey={card} onCardClick={(key) => setCard(card === key ? "all" : key)} />}
    >
      {shownOrphans.length > 0 && (
        <Alert className="fin-cash-flow__orphans" type="warning" showIcon
          message={`${shownOrphans.length} 条异常找不到对应流水`}
          description={<ul>{shownOrphans.map((item) => { const approval = item.serial ? approvals.get(item.serial) : undefined; return (
            <li key={item.id}><Tag bordered={false} color="red">{alertShort(item.type)}</Tag>
              {item.acct ? `${item.date} · ${accountMap.get(item.acct)?.name ?? item.acct} · ` : item.serial ? "" : `${item.date} · ${EMPTY} · `}{item.msg}
              {approval ? <Button type="link" size="small" onClick={() => setApprovalOpen(approval)}>看审批单</Button> : null}
              {ALERT_GUIDE[item.type] ? <Typography.Text type="secondary">（处理：{ALERT_GUIDE[item.type].guide}）</Typography.Text> : null}</li>); })}</ul>} />
      )}
      <BoardTable<CashLine> label="日记账表格" rowKey="id" rows={rows} columns={lineColumns} emptyTitle={refHint ? "没有对应的流水" : "暂无流水"} emptyText={refHint || (alertTypes.length && shownOrphans.length ? "选中的异常没有对应流水，见上方提示条" : "当前筛选下没有流水")} />
      {messageHolder}
      <RuntimeColumnConfigDrawer open={columnConfigOpen} groups={JOURNAL_COLUMN_GROUPS} fixedKeys={JOURNAL_FIXED_KEYS} defaultKeys={JOURNAL_DEFAULT_KEYS} appliedKeys={columnKeys} onApply={applyColumns} onClose={() => setColumnConfigOpen(false)} onSaveTemplate={() => void messageApi.info("列模板暂未开放；当前列配置仅保存在本浏览器")} />
      <Modal open={Boolean(rejecting)} title={rejecting?.level === 2 ? "终审不通过 · 驳回到待初审" : "初审不通过"} okText="确定不通过" okButtonProps={{ danger: true, disabled: !rejectReason.trim() }} cancelText="取消" onOk={confirmReject} onCancel={() => { setRejecting(undefined); setRejectReason(""); }} destroyOnHidden>
        {rejecting && <Typography.Paragraph type="secondary">{rejecting.line.date} · {accountMap.get(rejecting.line.acct)?.name ?? rejecting.line.acct} · {rejecting.line.masked ? "****" : fmtMoney(rejecting.line.amt, rejecting.line.cur)}</Typography.Paragraph>}
        <Input.TextArea autoFocus rows={3} maxLength={200} showCount placeholder="必填：不通过的原因（会显示在审核状态下，财务专员据此修改）" value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} />
      </Modal>
      <Modal open={Boolean(noting)} title="初审通过 · 写差额说明" okText="初审通过" okButtonProps={{ disabled: !noteText.trim() }} cancelText="取消" onOk={confirmNote} onCancel={() => { setNoting(undefined); setNoteText(""); }} destroyOnHidden>
        {noting && <Typography.Paragraph>审批单金额和这笔流水对不上：<Typography.Text type="danger">差额 {fmtMoney(amountDiff(noting, approvalsOf(noting)), noting.cur)}</Typography.Text>（审批单合计 − 流水金额）。写清楚原因，终审会看到。</Typography.Paragraph>}
        <Input.TextArea autoFocus rows={3} placeholder="必填：为什么有差额（例如：手续费由我方承担、分两笔付、汇率差……）" value={noteText} onChange={(event) => setNoteText(event.target.value)} />
      </Modal>
      <Modal open={Boolean(excluding)} title="剔除这笔流水" okText="确定剔除" okButtonProps={{ danger: true, disabled: !excludeReason.trim() }} cancelText="取消" onOk={confirmExclude} onCancel={() => { setExcluding(undefined); setExcludeAmount(""); setExcludeReason(""); }} destroyOnHidden>
        {excluding && <Typography.Paragraph type="secondary">{excluding.date} · {accountMap.get(excluding.acct)?.name ?? excluding.acct} · {fmtMoney(excluding.amt, excluding.cur)}。剔除只是不算本公司收支，不改银行余额。</Typography.Paragraph>}
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Input aria-label="剔除金额" placeholder="剔除金额（原币）；不填就是整笔" value={excludeAmount} onChange={(event) => setExcludeAmount(event.target.value)} />
          <Input.TextArea rows={3} maxLength={200} showCount placeholder="必填：为什么剔除" value={excludeReason} onChange={(event) => setExcludeReason(event.target.value)} />
        </Space>
      </Modal>
      <LineDrawer line={freshLine} review={freshLine ? reviewOf(freshLine) : undefined} data={data} details={details} approvalsOf={approvalsOf} alerts={freshLine ? alertsOf(freshLine) : []} live={live} onClose={() => setLineOpen(undefined)} onOpenApproval={setApprovalOpen}
        onPass={(line) => pass(line, 2)} onReject={(line) => setRejecting({ line, level: 2 })} onExclude={setExcluding} onUnexclude={(line) => void send(line, "unexclude", {}, "已撤销剔除")} />
      <ApprovalDrawer item={approvalOpen} data={data} details={details} onClose={() => setApprovalOpen(undefined)} />
      <ImportDrawer open={importOpen} live={live} onClose={() => setImportOpen(false)} />
    </FinanceBoardFrame>
  );
}
