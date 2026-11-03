/** 物流 sidebar section (Rocky 2026-11-03): 物流总览 / 到货预测 / 异常与提醒 / 时效与阈值设置 / 货代看板. */
import type { NavigationPage } from "@/config/navigation";
import LogisticsAlertsPage from "./LogisticsAlertsPage";
import LogisticsCarriersPage from "./LogisticsCarriersPage";
import LogisticsForecastPage from "./LogisticsForecastPage";
import LogisticsOverviewPage from "./LogisticsOverviewPage";
import LogisticsRulesPage from "./LogisticsRulesPage";

export default function LogisticsPages({ page, scope = "anonymous" }: { page: NavigationPage; scope?: string }) {
  switch (page.key) {
    case "pmc_logistics_forecast":
      return <LogisticsForecastPage page={page} scope={scope} />;
    case "pmc_logistics_alerts":
      return <LogisticsAlertsPage page={page} scope={scope} />;
    case "pmc_logistics_settings":
      return <LogisticsRulesPage page={page} scope={scope} />;
    case "pmc_logistics_carriers":
      return <LogisticsCarriersPage page={page} scope={scope} />;
    default:
      return <LogisticsOverviewPage page={page} scope={scope} />;
  }
}
