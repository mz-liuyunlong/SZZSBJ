/**
 * 财务板块页面分配表（总管维护）：每个财务标签只指向自己组的文件夹，10 组互不改同一个文件。
 * 新增 / 改名标签只改这里和 config/navigation.ts，路由文件 router/routes.tsx 不再逐个列财务页面。
 */
import type { NavigationPage } from "@/config/navigation";
import FinanceCashFlowPage from "@/pages/finance/FinanceCashFlowPage";
import FinancePlaceholderPage from "@/pages/finance/FinancePlaceholderPage";

type PageComponent = (props: { page: NavigationPage }) => React.JSX.Element;

// 其他标签各自提 PR 时再加回
const PAGES: Record<string, PageComponent> = {};

const CASH_VIEWS = { finance_cash_journal: "journal", finance_cash_stock: "stock", finance_cash_anomalies: "anomalies" } as const;

function FinancePageSwitch({ page }: { page: NavigationPage }) {
  if (page.key.startsWith("finance_cash_")) {
    // 第 7 组：资金流水 4 段共用一个页面文件
    const view = CASH_VIEWS[page.key as keyof typeof CASH_VIEWS] ?? "accounts";
    return <FinanceCashFlowPage page={page} view={view} />;
  }
  const Page = PAGES[page.key] ?? FinancePlaceholderPage;
  return <Page page={page} />;
}

export default FinancePageSwitch;
