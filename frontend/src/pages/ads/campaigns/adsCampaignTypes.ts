export type AdsCampaignMainTab = "delivery" | "reports" | "system";

export type CampaignType = "SP" | "SB" | "SV";
export type CampaignStatus = "enabled" | "paused" | "ended";
export type CampaignSearchField = "name" | "campaignId" | "account";
export type CampaignDatePreset = "today" | "week" | "month" | "year" | "custom";

export type CampaignDetailTab =
  | "adGroups"
  | "placements"
  | "pageTypes"
  | "platforms"
  | "adItems"
  | "keywords"
  | "negatives"
  | "searchTerms";

export interface AdsCampaign {
  id: string;
  account: string;
  name: string;
  type: CampaignType;
  target: string;
  status: CampaignStatus;
  startDate: string;
  endDate: string;
  budgetType: string;
  totalBudget: string;
  dailyBudget: number;
  spend: number;
  spendShare: number;
  impressions: number;
  impressionShare: number;
  clicks: number;
  clickShare: number;
  ctr: number;
  cpc: number;
  orders: number;
  sales: number;
  acos: number;
  roas: number;
}

export interface CampaignFilters {
  accounts: string[];
  datePreset?: CampaignDatePreset;
  dateRange?: [string, string];
  adTypes: CampaignType[];
  statuses: CampaignStatus[];
  searchField: CampaignSearchField;
  keyword: string;
}

export interface CampaignDetailRow {
  id: string;
  status?: CampaignStatus;
  account?: string;
  name: string;
  type?: string;
  scope?: string;
  source?: string;
  campaignName?: string;
  adGroupName?: string;
  createdAt?: string;
  bid?: number;
  multiplier?: string;
  spend?: number;
  impressions?: number;
  clicks?: number;
  ctr?: number;
  orders?: number;
  sales?: number;
  acos?: number;
  roas?: number;
  suggestion?: string;
  itemId?: string;
  matchType?: string;
  reviewStatus?: string;
  spendShare?: number;
  impressionShare?: number;
  clickShare?: number;
  cpc?: number;
  orderShare?: number;
  salesShare?: number;
  units?: number;
  unitShare?: number;
  cvr?: number;
  aov?: number;
  cpa?: number;
  directSales?: number;
  associatedSales?: number;
  productName?: string;
  productId?: string;
  baseBid?: number;
  availableQuantity?: number;
  suggestedBid?: number;
  placementName?: string;
  biddingStrategy?: string;
  bidAdjustment?: string;
  startDate?: string;
  endDate?: string;
  budgetType?: string;
  totalBudget?: number;
  dailyBudget?: number;
}

export interface ReportTaskRow {
  id: string;
  reportType: string;
  dateRange: string;
  status: "completed" | "running" | "failed";
  createdAt: string;
}

export interface SearchTermRow {
  id: string;
  term: string;
  campaignName: string;
  keyword: string;
  spend: number;
  clicks: number;
  orders: number;
  sales: number;
  acos: number | null;
  suggestion: "keyword" | "negative";
}

export interface RecommendationRow {
  id: string;
  type: string;
  target: string;
  reason: string;
  action: string;
  impact: string;
}

export interface SnapshotRow {
  id: string;
  type: string;
  entity: string;
  status: "completed" | "running" | "failed";
  createdAt: string;
}
