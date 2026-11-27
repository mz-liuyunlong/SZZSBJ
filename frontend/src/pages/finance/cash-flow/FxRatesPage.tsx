/**
 * 财务设置 · 资金 汇率。全系统汇率来自领星月汇率，这里不能改，只能手动同步；一页一个完整年份。
 * 正式构建读 /api/finance/cashflow/fx-rates，开发环境读 Demo 快照。
 */
import { Button, Select, Space, Tooltip, message } from "antd";
import type { ProColumns } from "@ant-design/pro-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { backendRequest } from "@/api/backendApi";
import { fetchCurrentUser } from "@/pages/auth/authApi";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import FinanceBoardFrame, { LOCKED_TIP } from "@/pages/finance/FinanceBoardFrame";
import { BoardTable } from "@/pages/finance/cash-flow/BoardTable";
import HelpButton from "@/pages/finance/cash-flow/HelpButton";
import { diffFxRates, fxAdjacentYear, FX_PAIR_LABEL, fxReadDenied, FX_SOURCE_LABEL, FX_SYNC_SUPER_ADMIN_ONLY, fxRateText, fxSyncDoneText, fxSyncErrorText, fxSyncFailedText, fxYearRows, fxYears, type FxRateRow, type FxSyncState } from "@/pages/finance/cash-flow/fxRates";
import { cashErrorText, isCashLive } from "@/pages/finance/cash-flow/journalApi";
import { useCashSnapshot } from "@/pages/finance/localFinData";
import "@/pages/finance/cash-flow/cash-flow.css";

const RATES_URL = "/api/finance/cashflow/fx-rates";
const SYNC_KEY = ["finance", "fx-rates", "sync"];
const isActive = (status?: string) => status === "queued" || status === "running";

const COLUMNS: ProColumns<FxRateRow>[] = [
  { title: "月份", dataIndex: "month", width: 140 },
  { title: "币种", key: "pair", width: 140, render: () => FX_PAIR_LABEL },
  { title: "月汇率", key: "rate", width: 140, align: "right", render: (_, row) => fxRateText(row.rate) },
  { title: "来源", key: "source", width: 280, render: (_, row) => (fxRateText(row.rate) === "—" ? "—" : FX_SOURCE_LABEL) },
];

function FxRatesHelp() {
  return (
    <HelpButton
      title="资金 汇率"
      sections={[
        { title: "数据从哪来", body: "每月一个美元兑人民币汇率，取领星的「我的汇率」。这里不能改，要改请到领星改，再点「手动同步」。系统每周一也会自动同步一次。" },
        { title: "手动同步", body: "从本月往回拉 13 个月。完成后提示新增、更新、未变各几条；这里只数美元这一行。" },
        { title: "日记账怎么用", body: "美元流水按业务日所在月的汇率折人民币。当月没有汇率时显示「—」，不用别的月份代替。" },
      ]}
    />
  );
}

function FxRatesPage({ page }: { page: NavigationPage }) {
  const client = useQueryClient();
  const [messageApi, messageHolder] = message.useMessage();
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const live = useQuery({
    queryKey: ["finance", "fx-rates"],
    enabled: isCashLive,
    retry: false,
    queryFn: async () => (await backendRequest<{ month: string; my_rate: string | null }[]>(RATES_URL)).data,
  });
  const demo = useCashSnapshot();
  const syncState = useQuery({
    queryKey: SYNC_KEY,
    enabled: isCashLive,
    retry: false,
    refetchInterval: (query) => (isActive(query.state.data?.status) ? 3000 : false),
    queryFn: async () => (await backendRequest<FxSyncState>(`${RATES_URL}/sync`)).data,
  });
  const currentUser = useQuery({
    queryKey: ["finance", "fx-rates", "current-user"],
    enabled: isCashLive,
    retry: false,
    staleTime: 30_000,
    queryFn: fetchCurrentUser,
  });
  const liveRows = (data?: { month: string; my_rate: string | null }[]): FxRateRow[] =>
    (data ?? []).map((row) => ({ month: row.month, rate: row.my_rate }));
  /* 记下点按钮前的汇率和这次的任务号，任务结束后对比出新增、更新、未变。 */
  const pending = useRef<{ runId: string | null; before: FxRateRow[] } | null>(null);
  const start = useMutation({
    mutationFn: async () => (await backendRequest<FxSyncState>(`${RATES_URL}/sync`, { method: "POST" })).data,
    onMutate: () => ({ before: liveRows(live.data) }),
    onSuccess: (data, _variables, context) => {
      pending.current = { runId: data.run_id, before: context.before };
      client.setQueryData(SYNC_KEY, data);
    },
    onError: (error) => { void messageApi.error(fxSyncErrorText(error)); },
  });
  const runId = syncState.data?.run_id;
  const status = syncState.data?.status;
  const errorCode = syncState.data?.error_code ?? null;
  const { refetch } = live;
  useEffect(() => {
    const waiting = pending.current;
    if (!waiting || waiting.runId !== runId || isActive(status)) return;
    pending.current = null;
    void refetch().then((result) => {
      if (status === "succeeded") void messageApi.success(fxSyncDoneText(diffFxRates(waiting.before, liveRows(result.data))));
      else void messageApi.error(fxSyncFailedText(errorCode));
    });
  }, [runId, status, errorCode, refetch, messageApi]);

  const rows: FxRateRow[] = isCashLive ? liveRows(live.data) : demo.data?.meta.fx_months ?? [];
  const failure = isCashLive && live.error ? cashErrorText(live.error) : null;
  const years = fxYears(rows, currentYear);
  const busy = start.isPending || isActive(status);
  const isSuperAdmin = currentUser.data?.isSuperAdmin === true;
  /* 还没查到身份时先置灰但不提示；查到不是超管（或查询失败）才提示。真正的权限在后端，返回 403 时提示同一句话。 */
  const syncTip = !isCashLive ? LOCKED_TIP : !currentUser.isPending && !isSuperAdmin ? FX_SYNC_SUPER_ADMIN_ONLY : null;
  const syncButton = (
    <Button type="primary" loading={busy} disabled={!isCashLive || !isSuperAdmin || busy} onClick={() => start.mutate()}>
      {busy ? "同步中" : "手动同步"}
    </Button>
  );
  const olderYear = fxAdjacentYear(years, year, "older");
  const newerYear = fxAdjacentYear(years, year, "newer");
  return (
    <PageShell
      page={page}
      headerActions={(
        <Space size={8}>
          <Tooltip title={syncTip}>{syncButton}</Tooltip>
          <FxRatesHelp />
        </Space>
      )}
    >
      {messageHolder}
      <FinanceBoardFrame
        title="资金 汇率"
        loading={isCashLive ? live.isPending : demo.isPending}
        preview={!isCashLive}
        toolbar={(
          <Space size={8}>
            <Button aria-label="上一年" disabled={olderYear == null} onClick={() => { if (olderYear != null) setYear(olderYear); }}>‹</Button>
            <Select aria-label="年份" style={{ width: 110 }} value={year} onChange={setYear} options={years.map((value) => ({ value, label: `${value} 年` }))} />
            <Button aria-label="下一年" disabled={newerYear == null} onClick={() => { if (newerYear != null) setYear(newerYear); }}>›</Button>
          </Space>
        )}
      >
        {failure ? (
          <BoardTable<FxRateRow> label="资金 汇率" rowKey="month" rows={[]} columns={COLUMNS} emptyTitle={fxReadDenied(live.error) ? "没有权限" : "汇率读取失败"} emptyText={fxReadDenied(live.error) ? "只有超级管理员能查看汇率" : failure} />
        ) : (
          <BoardTable<FxRateRow> label="资金 汇率" rowKey="month" rows={fxYearRows(rows, year)} columns={COLUMNS} emptyTitle="还没有汇率" emptyText="点「手动同步」从领星拉取" />
        )}
      </FinanceBoardFrame>
    </PageShell>
  );
}

export default FxRatesPage;
