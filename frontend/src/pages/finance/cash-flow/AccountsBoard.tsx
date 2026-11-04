/** 账户总览（按月）；从 FinanceCashFlowPage.tsx 原样搬出。 */
import { Button, Tag, Tooltip, Typography } from "antd";
import { type ProColumns } from "@ant-design/pro-components";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import ManagementStatCards, { type ManagementStatCardItem } from "@/components/report-table/ManagementStatCards";
import FinanceBoardFrame, { FinMoney, LOCKED_TIP } from "@/pages/finance/FinanceBoardFrame";
import { useApprovals } from "@/pages/finance/cash-flow/data";
import { fmtMoney, type CashAccount, type CashFlowMonth, type CashSnapshot } from "@/pages/finance/localFinData";
import ReportFacetSelect from "@/shared/report-filters";
import { type JournalHandoff, KIND_COLOR, EMPTY, isUncat, NO_FLOW_TYPE, mergeFeishu, noFlowAlerts, orphanInScope, icon, writeHandoff } from "@/pages/finance/cash-flow/journalShared";
import { BoardTable } from "@/pages/finance/cash-flow/BoardTable";

/* ======================================================= 账户总览（按月） */
export function AccountsBoard({ data }: { data: CashSnapshot }) {
  const navigate = useNavigate();
  const months = data.flow.months;
  const [month, setMonth] = useState(months[months.length - 1] ?? "");
  const overviewFile = useApprovals();
  const overviewDetails = useMemo(() => overviewFile.data?.items ?? {}, [overviewFile.data]);
  /* 当月没有汇率就不折算：美元不计入合计，副标题提示缺汇率（不再按 7 估）。 */
  const fx = data.meta.fx[month]?.[0];
  const coverage = useMemo(() => {
    const out: Record<string, { from: string; to: string; src: string }> = {};
    (data.meta.bank_files ?? []).forEach((file) => {
      (file.accts ?? (file.acct ? [file.acct] : [])).forEach((acct) => {
        const next = { from: file.range_from || file.from || "", to: file.range_to || file.to || "", src: file.range_src || "流水" };
        if (!out[acct] || next.to > out[acct].to) out[acct] = next;
      });
    });
    return out;
  }, [data]);
  type Row = CashAccount & CashFlowMonth & { n_lines: number; uncat: number };
  const rows: Row[] = data.accounts.map((account) => {
    const lines = data.lines.filter((line) => line.acct === account.id && line.m === month);
    return { ...account, ...(data.flow.by_acct[account.id]?.[month] ?? {}), n_lines: lines.length, uncat: lines.filter(isUncat).length };
  });
  const toCny = (row: Row, value: number | null | undefined) => (value == null ? 0 : row.cur !== "USD" ? value : fx == null ? 0 : value * fx);
  const fxNote = fx == null ? "缺 USD 汇率，合计不含美元" : `汇率 ${fx}`;
  const inExt = rows.reduce((total, row) => total + toCny(row, row.in_ext), 0);
  const outExt = rows.reduce((total, row) => total + toCny(row, row.out_ext), 0);
  const noFlow = noFlowAlerts(data, mergeFeishu(data, overviewDetails)).filter((item) => orphanInScope(item, [], month)).length;
  const uncat = data.lines.filter((line) => line.m === month && isUncat(line)).length;
  const openJournal = (handoff: JournalHandoff) => { writeHandoff(handoff); navigate("/finance/cash/journal"); };
  const cards: ManagementStatCardItem<string>[] = [
    { key: "in", title: `${month} 外部流入`, subtitle: `折人民币 · 不含内部调拨 / 结汇 / 归集${fx == null ? ` · ${fxNote}` : ""}`, value: fmtMoney(inExt), tone: "success", icon: icon("入") },
    { key: "out", title: `${month} 外部流出`, subtitle: `折人民币 · ${fxNote}`, value: fmtMoney(outExt), tone: "danger", icon: icon("出") },
    { key: "uncat", title: "待分类流水", subtitle: "点击到日记账处理", value: uncat, tone: uncat ? "warning" : "normal", icon: icon("?") },
    { key: "no_flow", title: NO_FLOW_TYPE, subtitle: "飞书已同意、没有付款流水，点击到日记账", value: noFlow, tone: noFlow ? "warning" : "normal", icon: icon("单") },
    { key: "pairs", title: "内部配对", subtitle: `未配对 ${data.meta.summary.unpaired ?? 0}`, value: `${data.meta.summary.pairs ?? 0} 对`, tone: "normal", icon: icon("⇄") },
  ];
  const columns: ProColumns<Row>[] = [
    { title: "账户", dataIndex: "name", width: 280, fixed: "left", render: (_, row) => <Typography.Text strong>{row.name}</Typography.Text> },
    { title: "类型", dataIndex: "kind", width: 80, render: (_, row) => <Tag bordered={false} color={KIND_COLOR[row.kind]}>{row.kind}</Tag> },
    { title: "币种", dataIndex: "cur", width: 70 },
    { title: "流水覆盖", width: 190, tooltip: "表头声明的查询区间优先；没有的按文件首末两笔；区间内没有行 = 该段无交易", render: (_, row) => { const cov = coverage[row.id]; return cov ? <span className="finance-board__stack">{cov.from} ~ {cov.to}<span className="finance-board__sub">{cov.src === "表头" ? "表头声明" : "按首末笔"}</span></span> : EMPTY; } },
    { title: "期初", dataIndex: "open", width: 140, align: "right", render: (_, row) => <FinMoney value={row.open} cur={row.cur} /> },
    { title: "外部流入", dataIndex: "in_ext", width: 140, align: "right", render: (_, row) => <FinMoney value={row.in_ext} cur={row.cur} /> },
    { title: "外部流出", dataIndex: "out_ext", width: 140, align: "right", render: (_, row) => <FinMoney value={row.out_ext} cur={row.cur} /> },
    { title: "内部净", width: 130, align: "right", render: (_, row) => <FinMoney value={(row.in_int ?? 0) + (row.out_int ?? 0)} cur={row.cur} /> },
    { title: "期末（算）", dataIndex: "close", width: 140, align: "right", render: (_, row) => <FinMoney value={row.close} cur={row.cur} /> },
    { title: "表中期末", dataIndex: "sheet_close", width: 140, align: "right", tooltip: "余额链链尾；与期末（算）差 > 1 元说明漏行或行序错", render: (_, row) => (row.sheet_close == null ? <Typography.Text type="secondary">无余额列</Typography.Text> : <FinMoney value={row.sheet_close} cur={row.cur} />) },
    { title: "行数", dataIndex: "n_lines", width: 80, align: "right", render: (_, row) => (row.n_lines ? <Button type="link" size="small" onClick={() => openJournal({ account: row.id })}>{row.n_lines}</Button> : 0) },
    { title: "待分类", dataIndex: "uncat", width: 80, align: "right", render: (_, row) => (row.uncat ? <Tag color="red" bordered={false}>{row.uncat}</Tag> : 0) },
  ];
  return (
    <FinanceBoardFrame
      title="账户总览（按月）"
      subtitle={`起点 ${data.meta.start} · 构建 ${data.meta.built} · 银行 / 平台导出 ${(data.meta.bank_files ?? []).length} 份`}
      toolbar={<>
        <ReportFacetSelect ariaLabel="月份" placeholder="月份" value={month} allowClear={false} showSearch={false} options={months.map((value) => ({ value, label: value }))} onChange={(value) => setMonth(String(value ?? months[months.length - 1]))} />
        <span className="finance-board__toolbar-actions"><Tooltip title={LOCKED_TIP}><Button disabled>导出 Excel</Button></Tooltip></span>
      </>}
      summary={<ManagementStatCards<string> ariaLabel="账户总览统计" className="finance-board__summary finance-board__summary--5" cards={cards} activeKey="" onCardClick={(key) => { if (key === "uncat") openJournal({ cats: ["NONE"], month }); if (key === "no_flow") openJournal({ alerts: [NO_FLOW_TYPE], month }); }} />}
    >
      <BoardTable<Row> label="账户总览表格" rowKey="id" rows={rows} columns={columns} emptyTitle="暂无账户" emptyText="还没有导入任何现金流账户报表" pageSize={50} />
    </FinanceBoardFrame>
  );
}
