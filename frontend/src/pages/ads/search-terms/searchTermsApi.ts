import { backendRequest } from "@/api/backendApi";

export interface SearchTermRow {
  id: string;
  business_date_la: string;
  source_account_ref: string;
  advertiser_id: string;
  store_id: string | null;
  item_id: string | null;
  listing_mapping_status: string;
  mp_seller_name: string | null;
  mp_advertiser_name: string | null;
  campaign_id: string;
  campaign_name: string | null;
  targeting_type: string;
  searched_keyword: string;
  num_ads_shown: number | null;
  num_ads_clicks: number | null;
  ad_spend_amount: string | null;
  attributed_orders: string | null;
  advertised_sku_sales_amount: string | null;
  other_sku_sales_amount: string | null;
  cpc: string | null;
  ctr: string | null;
  cvr: string | null;
  attribution_days: number;
  synced_at: string;
}

export interface SearchTermQuery {
  start_date: string;
  end_date: string;
  store_ids?: string[];
  advertiser_ids?: string[];
  campaign_ids?: string[];
  targeting_type?: "all" | "auto" | "manual";
  query?: string;
  conversion_state?: "all" | "orders" | "no_orders";
  page?: number;
  page_size?: number;
}

export interface SearchTermListData {
  items: SearchTermRow[];
  total: number;
  page: number;
  page_size: number;
  view: "summary" | "detail";
}

export interface SearchTermSummary {
  total_terms: number;
  converting_terms: number;
  auto_converting_not_manually_covered: number;
  no_order_terms_with_spend: number;
  ad_spend_total: string;
  attributed_orders_total: string;
  direct_sales_total: string;
  other_sales_total: string;
  freshness_at: string | null;
  mapping_unresolved_count: number;
}

export interface SearchTermTrendPoint {
  business_date_la: string;
  impressions: number;
  clicks: number;
  spend: string;
  orders: string;
  direct_sales: string;
  other_sales: string;
}

export interface SearchTermAction {
  id: string;
  source_account_ref: string;
  source_fact_id: string | null;
  action_type: string;
  search_term: string;
  target_scope_json: Record<string, unknown>;
  status: string;
  effect_status: string;
  reason: string;
  created_by: string;
  completed_by: string | null;
  completion_note: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

const params = (query: Record<string, unknown>) => {
  const searchParams = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) {
      value.forEach((item) => searchParams.append(key, String(item)));
    } else {
      searchParams.set(key, String(value));
    }
  });
  return searchParams.toString();
};

export async function listSearchTerms(query: SearchTermQuery) {
  return (
    await backendRequest<SearchTermListData>(
      `/api/ads/search-terms?${params(query)}`,
    )
  ).data;
}

export async function getSearchTermSummary(query: SearchTermQuery) {
  return (
    await backendRequest<SearchTermSummary>(
      `/api/ads/search-terms/summary?${params(query)}`,
    )
  ).data;
}

export async function getSearchTermTrends(
  term: string,
  startDate: string,
  endDate: string,
) {
  return (
    await backendRequest<{ items: SearchTermTrendPoint[]; date_grain: "daily_snapshot" }>(
      `/api/ads/search-terms/trends?${params({
        term,
        start_date: startDate,
        end_date: endDate,
      })}`,
    )
  ).data;
}

export async function listSearchTermActions(page = 1, pageSize = 50) {
  return (
    await backendRequest<{ items: SearchTermAction[]; total: number }>(
      `/api/ads/search-terms/actions?${params({
        page,
        page_size: pageSize,
      })}`,
    )
  ).data;
}

export async function createSearchTermAction(input: {
  source_account_ref: string;
  source_fact_id?: string;
  action_type: "add_keyword" | "add_negative_keyword";
  search_term: string;
  target_scope: Record<string, unknown>;
  reason: string;
}) {
  return (
    await backendRequest<SearchTermAction>("/api/ads/search-terms/actions", {
      method: "POST",
      body: JSON.stringify(input),
    })
  ).data;
}

export async function completeSearchTermAction(
  id: string,
  completion_note: string,
) {
  return (
    await backendRequest<SearchTermAction>(
      `/api/ads/search-terms/actions/${encodeURIComponent(id)}/complete`,
      {
        method: "PATCH",
        body: JSON.stringify({ completion_note }),
      },
    )
  ).data;
}
