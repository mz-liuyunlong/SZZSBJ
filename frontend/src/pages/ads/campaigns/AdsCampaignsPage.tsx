import { Tabs } from "antd";
import PageShell from "@/components/page/PageShell";
import type { NavigationPage } from "@/config/navigation";
import { usePageStateCache } from "@/shared/page-state/pageStateCache";
import type { AdsCampaignMainTab } from "@/pages/ads/campaigns/adsCampaignTypes";
import DeliveryManagementTab from "@/pages/ads/campaigns/tabs/DeliveryManagementTab";
import AdsReportsTab from "@/pages/ads/campaigns/tabs/AdsReportsTab";
import SystemCapabilitiesTab from "@/pages/ads/campaigns/tabs/SystemCapabilitiesTab";
import "@/pages/ads/campaigns/AdsCampaignsPage.css";

interface AdsCampaignsPageProps {
  page: NavigationPage;
}

function AdsCampaignsPage({ page }: AdsCampaignsPageProps) {
  const [activeTab, setActiveTab] = usePageStateCache<AdsCampaignMainTab>(
    `ads-campaigns:${page.key}:main-tab`,
    "delivery",
  );

  return (
    <PageShell page={page}>
      <div className="ads-campaigns-page">
        <Tabs
          className="ads-campaigns-page__main-tabs"
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as AdsCampaignMainTab)}
          items={[
            {
              key: "delivery",
              label: "投放管理",
              children: <DeliveryManagementTab />,
            },
            {
              key: "reports",
              label: "数据报表",
              children: <AdsReportsTab />,
            },
            {
              key: "system",
              label: "系统能力",
              children: <SystemCapabilitiesTab />,
            },
          ]}
        />
      </div>
    </PageShell>
  );
}

export default AdsCampaignsPage;
