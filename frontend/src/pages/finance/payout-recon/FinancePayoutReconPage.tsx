/**
 * 财务 · 回款对账（Rocky 2026-11-08 / 11-09 方案，11-10 批准上线规则）：
 * - 一期 = 一次打款（账单日），每店一行；默认最新一期，可多选几期。2026-10-01 起的账单才对账。
 * - 自动配对：账单日后 0–7 天、到这家店的收款账户、金额差 ≤ 0.01；合并打款也自动配；对不上的在详情里手动配。
 * - 确认到账 = 初审，财务主管终审（同日记账）；打款异常写跟进。
 * - 「收款账户匹配」在「手动同步」旁边，点开抽屉。
 * 全部读写 /api/finance/payout-recon 和 /api/finance/walmart-bills/sync，没有本地预览数据。
 */
import { Button, Tooltip, Typography, message } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import FinanceBoardFrame from "@/pages/finance/FinanceBoardFrame";
import EmptyState from "@/shared/states/EmptyState";
import AccountMapDrawer from "./AccountMapDrawer";
import HelpButton, { type HelpSection } from "./HelpButton";
import PeriodDrawer from "./PeriodDrawer";
import ReconBoard from "./ReconBoard";
import {
  autoMatch,
  isForbidden,
  postFollow,
  postReview,
  reconErrorText,
  startBillSync,
  toRow,
  useBillSync,
  usePayoutPeriods,
  useReconRefresh,
  type ApiPeriodList,
  type ReconRow,
} from "./reconApi";
import { timeText } from "./reconModel";
import "./payout-recon.css";

const HELP: HelpSection[] = [
  { title: "这页做什么", body: "沃尔玛每期打款到账后，和沃尔玛账单一期一期对上，并和日记账里的收款流水配对。人工只做两件事：确认到账、跟进打款异常。只对 2026-10-01 起的账单。" },
  { title: "一期", body: "一期 = 一次打款日（账单日），每店一行。默认看最新一期；「账单日」里打勾选一期或几期，全选（或都不选）= 全部期；多期时按账单日从新到旧排。" },
  { title: "自动配对", body: "到账日期在账单日之后 0–7 天、到了这家店的收款账户（填了收款账户识别的还要对上付款邮箱 / 公司名）、金额差不超过 0.01，就自动配上；一笔到账等于几期应付相加（合并打款）也自动配。几笔对不清的不自动配，在详情里手动配。配上后日记账那笔的备注写「平台回款 · 店铺 · 账单日」，分类是空的自动填「平台回款」；撤销配对时恢复。" },
  { title: "状态", body: "已打款；金额不符（差超过 ±0.01）、账单日过 7 天还没到账、账单作废，都算「打款异常」，所有期次都放进「打款异常」卡片里跟进 Case。账单日后 7 天内显示「等到账」；应付 ≤ 0 或不可付的显示「不需打款」。" },
  { title: "跟进", body: "打款异常由财务专员跟进：点「最新跟进」旁的铅笔，填 Case 编号、下次跟进时间和跟进记录（格式同 WFS 费用异常总表），每次保存追加一条，详情里看全部。" },
  { title: "审核", body: "同日记账：配上到账的期次，财务专员在「审核」列点 ✓ = 确认到账（初审）；然后变成终审，财务主管点 ✓ 终审通过、点 ✗ 写原因驳回到待初审。初审、终审、跟进分开授权。已初审 / 终审的不能改配对，要先终审驳回。" },
  { title: "收款账户匹配", body: "「手动同步」旁边的按钮。一个店铺一个收款账户：收款机构是 PingPong / 派安盈，收款账户派安盈是邮箱、PingPong 是公司名称，另记钱进日记账的哪个账户；换账户后旧的进「历史账户」。改这里要终审权限。" },
  { title: "手动同步", body: "沃尔玛账单每周三凌晨自动从领星拉一次；有权限的人可以点「手动同步」马上拉（重拉最近 35 天）。" },
];

function ReconWorkbench({ data }: { data: ApiPeriodList }) {
  const refresh = useReconRefresh();
  const sync = useBillSync();
  const rows = useMemo(() => data.items.map(toRow), [data]);
  const payDates = useMemo(() => Array.from(new Set(rows.map((row) => row.payDate))).sort().reverse(), [rows]);
  const [picked, setPicked] = useState<string[]>(payDates[0] ? [payDates[0]] : []);
  const [mapOpen, setMapOpen] = useState(false);
  const [opened, setOpened] = useState<string>();
  const [messageApi, messageHolder] = message.useMessage();
  const tried = useRef(false);

  // 进页面时有能自动配上的就配一次（没有初审权限的人跳过，不打扰）。
  useEffect(() => {
    if (tried.current || data.auto_ready <= 0) return;
    tried.current = true;
    autoMatch()
      .then((result) => {
        if (result.matched_periods) void messageApi.success(`自动配对 ${result.matched_periods} 期`);
        void refresh();
      })
      .catch((error: unknown) => { if (!isForbidden(error)) void messageApi.error(reconErrorText(error)); });
  }, [data.auto_ready, messageApi, refresh]);

  const act = async (work: () => Promise<unknown>, done: string) => {
    try {
      await work();
      void messageApi.success(done);
      await refresh();
    } catch (error) {
      void messageApi.error(reconErrorText(error));
    }
  };
  const runSync = async () => {
    try {
      await startBillSync();
      void messageApi.success("已发起同步，完成后刷新页面看最新账单");
      void sync.refetch();
    } catch (error) {
      void messageApi.error(reconErrorText(error));
    }
  };
  const syncText = sync.data ? (sync.data.status === "running" || sync.data.status === "queued" ? "同步中…" : `最后同步成功：${timeText(sync.data.last_success_at)}`) : "—";
  const actions = (
    <>
      <Typography.Text type="secondary">沃尔玛账单{syncText}</Typography.Text>
      <Button onClick={() => setMapOpen(true)}>收款账户匹配</Button>
      <Tooltip title="马上从领星重拉最近 35 天的沃尔玛账单（要手动同步权限）">
        <Button loading={sync.data?.status === "running" || sync.data?.status === "queued"} onClick={() => void runSync()}>手动同步</Button>
      </Tooltip>
    </>
  );
  const openedRow = rows.find((row) => row.key === opened);
  const openRows = rows.filter((row) => !row.matchId && row.state !== "voided" && row.state !== "no_pay");

  return (
    <>
      {messageHolder}
      <ReconBoard
        actions={actions}
        subtitle={`对账从 ${data.recon_start} 起${data.truncated ? ` · 只显示最近 ${data.limit} 行` : ""}`}
        rows={rows}
        payDates={payDates}
        picked={picked}
        onPicked={setPicked}
        onPass={(row, level) => void act(() => postReview(level === 1 ? "review1_pass" : "review2_pass", [row]), level === 1 ? "已确认到账" : "终审通过")}
        onReject={(row, reason) => void act(() => postReview("review2_reject", [row], reason), "终审不通过，已驳回到待初审")}
        onFollowUp={async (row: ReconRow, values) => act(() => postFollow(row, values), "跟进已保存")}
        onBatchDone={() => void refresh()}
        onOpen={(row) => setOpened(row.key)}
      />
      <AccountMapDrawer open={mapOpen} onClose={() => setMapOpen(false)} onChanged={() => void refresh()} />
      <PeriodDrawer
        row={openedRow}
        openRows={openRows}
        onPass={(row) => void act(() => postReview("review2_pass", [row]), "终审通过")}
        onReject={(row, reason) => void act(() => postReview("review2_reject", [row], reason), "终审不通过，已驳回到待初审")}
        onChanged={() => void refresh()}
        onClose={() => setOpened(undefined)}
      />
    </>
  );
}

function FinancePayoutReconPage({ page }: { page: NavigationPage }) {
  const periods = usePayoutPeriods();
  return (
    <PageShell page={page} headerActions={<HelpButton title="回款对账" sections={HELP} />}>
      {periods.data ? <ReconWorkbench data={periods.data} /> : (
        <FinanceBoardFrame title="回款对账" loading={periods.isPending && !periods.error} subtitle="">
          <EmptyState title={periods.error ? "读取失败" : "加载中"} description={periods.error ? reconErrorText(periods.error) : "正在读取回款对账"} />
        </FinanceBoardFrame>
      )}
    </PageShell>
  );
}

export default FinancePayoutReconPage;
