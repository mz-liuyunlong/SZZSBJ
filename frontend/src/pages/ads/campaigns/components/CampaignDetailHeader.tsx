import { ArrowLeftOutlined, EyeOutlined } from "@ant-design/icons";
import { Button } from "antd";

import type { AdsCampaign, CampaignStatus } from "../adsCampaignTypes";

import "./CampaignDetailHeader.css";

interface CampaignDetailHeaderProps {
  campaign: AdsCampaign | null;
  onBack: () => void;
  onOpenSettings: () => void;
  onOpenOperationLog: () => void;
}

const fallback = "--";

const statusText: Record<CampaignStatus, string> = {
  enabled: "进行中",
  paused: "已暂停",
  ended: "已结束",
};

const formatValue = (value: string | number | undefined | null) => {
  if (value === undefined || value === null || value === "") return fallback;
  return String(value);
};

function CampaignDetailHeader({
  campaign,
  onBack,
  onOpenSettings,
  onOpenOperationLog,
}: CampaignDetailHeaderProps) {
  if (!campaign) return null;

  const detailItems = [
    { label: "状态", value: statusText[campaign.status] },
    { label: "活动类型", value: campaign.type },
    { label: "投放类型", value: campaign.target },
    { label: "每日预算", value: `$${campaign.dailyBudget}` },

    { label: "投放设置", value: fallback },
    { label: "竞价策略", value: "固定竞价" },
    { label: "Buy-Box", value: fallback },
    { label: "Search Ingrid", value: "0%" },

    { label: "Home Page", value: fallback },
    { label: "Stock Up", value: fallback },
    { label: "PC端", value: fallback },
    { label: "App", value: fallback },

    { label: "移动端", value: fallback },
    { label: "开始时间", value: campaign.startDate },
    {
      label: "结束时间",
      value: campaign.endDate && campaign.endDate !== "--" ? campaign.endDate : "无结束时间",
    },
  ];

  return (
    <div className="campaign-detail-header">
      <div className="campaign-detail-header__title-row">
        <div className="campaign-detail-header__title-main">
          <Button
            type="text"
            size="small"
            className="campaign-detail-header__back-button"
            icon={<ArrowLeftOutlined />}
            onClick={onBack}
          >
            返回
          </Button>

          <span className="campaign-detail-header__title-label">广告活动：</span>
          <span className="campaign-detail-header__title-name">{formatValue(campaign.name)}</span>

          <Button
            type="text"
            size="small"
            className="campaign-detail-header__icon-button"
            icon={<EyeOutlined />}
            aria-label="查看广告活动"
          />

          <Button
            type="link"
            size="small"
            className="campaign-detail-header__text-button"
            onClick={onOpenSettings}
          >
            广告活动设置
          </Button>

          <Button
            type="link"
            size="small"
            className="campaign-detail-header__text-button"
            onClick={onOpenOperationLog}
          >
            操作日志
          </Button>
        </div>
      </div>

      <div className="campaign-detail-header__meta-grid">
        {detailItems.map((item) => (
          <div key={item.label} className="campaign-detail-header__meta-item">
            <span className="campaign-detail-header__meta-label">{item.label}：</span>
            <span className="campaign-detail-header__meta-value">{formatValue(item.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default CampaignDetailHeader;
