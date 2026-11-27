/**
 * 财务 · 资金流水（本地预览阶段 A，只读）。左侧菜单「资金流水」：账户总览（按月）/ 日记账（备货资金暂从菜单隐藏，代码保留）。
 * 2026-11-04 Rocky：去掉「异常」页，资金异常全部并入日记账显示，不分等级（所有异常都要处理）。
 * 视觉与 PMC 采购看板一致：page card → 标题行 → 筛选卡（ReportFacetSelect / CommittedSearch / 重置）→ 统计卡（ManagementStatCards，点击即筛选）→ ProTable。
 * 日记账：开发环境读 localFinData（Demo 快照，写操作置灰）；正式构建读 /api/finance/cashflow（见 cash-flow/journalApi.ts）。账户总览、备货资金仍是 Demo。
 */
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import FinanceBoardFrame from "@/pages/finance/FinanceBoardFrame";
import CashStockBoard, { CashStockHelp } from "@/pages/finance/cash-flow/CashStockBoard";
import { cashErrorText, cashViewSource, isCashLive, useLiveJournal } from "@/pages/finance/cash-flow/journalApi";
import { useStock } from "@/pages/finance/cash-flow/data";
import "@/pages/finance/cash-flow/cash-flow.css";
import { useCashSnapshot } from "@/pages/finance/localFinData";
import EmptyState from "@/shared/states/EmptyState";
import { type CashFlowView } from "@/pages/finance/cash-flow/journalShared";
import { AccountsBoard } from "@/pages/finance/cash-flow/AccountsBoard";
import { JournalBoard } from "@/pages/finance/cash-flow/JournalBoard";

/** 资金流水下的左侧菜单页（2026-11-02 Rocky：做成资金流水的下一级菜单，UI 与正式系统一致；11-04 去掉「异常」页）。 */
function FinanceCashFlowPage({ page, view }: { page: NavigationPage; view: CashFlowView }) {
  /* 正式构建不读 Demo（localQuery 只在开发环境启用）：除接口版日记账外一律显示「建设中」，不再一直转圈。 */
  const source = cashViewSource(view, import.meta.env.DEV, isCashLive);
  const snapshot = useCashSnapshot();
  const liveJournal = source === "live";
  const liveQuery = useLiveJournal(liveJournal);
  const data = liveJournal ? liveQuery.data?.snapshot : snapshot.data;
  const pending = liveJournal ? liveQuery.isPending : snapshot.isPending;
  const failure = liveJournal ? liveQuery.error : snapshot.error;
  const fallbackTitle = { accounts: "账户总览（按月）", journal: "日记账", stock: "备货资金" }[view];
  const stock = useStock(view === "stock" && source === "demo");
  if (source === "building") return (
    <PageShell page={page}>
      <FinanceBoardFrame title={fallbackTitle} preview={false}>
        <EmptyState title="建设中" description="这一页的数据还没接正式接口" />
      </FinanceBoardFrame>
    </PageShell>
  );
  return (
    <PageShell page={page} headerActions={view === "stock" ? <CashStockHelp data={stock.data} /> : undefined}>
      {view === "stock" ? <CashStockBoard /> : !data ? (
        <FinanceBoardFrame title={fallbackTitle} loading={pending} preview={!liveJournal}>
          <EmptyState
            title={failure ? (liveJournal ? "日记账读取失败" : "本地预览数据未就绪") : "加载中"}
            description={failure ? (liveJournal ? cashErrorText(failure) : (failure as Error).message) : liveJournal ? "正在读取日记账" : "正在读取本地预览数据"}
          />
        </FinanceBoardFrame>
      ) : view === "accounts" ? <AccountsBoard data={data} />
        : <JournalBoard data={data} live={liveJournal} liveDetails={liveQuery.data?.details} />}
    </PageShell>
  );
}

export default FinanceCashFlowPage;
