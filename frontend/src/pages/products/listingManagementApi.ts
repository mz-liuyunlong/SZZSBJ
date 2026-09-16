import { backendRequest } from "@/api/backendApi";
import type { ListingManagementRow } from "@/pages/products/listingManagementData";

interface BackendListingItem {
  id: string;
  store_id: string;
  store_name: string | null;
  item_id: string;
  msku: string | null;
  local_sku: string | null;
  local_name: string | null;
  title: string | null;
  picture_url: string | null;
  owner_ref: string | null;
  product_grade: string | null;
  tags: string[];
  strike_price_amount: string | null;
  sale_price_amount: string | null;
  listing_status: string | null;
  lifecycle_status: string | null;
  listing_start_at_utc: string | null;
  category: string | null;
  wfs_available_quantity: string | null;
  inbound_quantity: string | null;
  sales_30d: string;
  ad_spend_30d_amount: string | null;
  buybox_status: string | null;
  walmart_seller: string | null;
  is_hijacked: boolean | null;
  average_rating: string | null;
  review_count: number | null;
  brand: string | null;
  disabled_reason: string | null;
  gtin: string | null;
  calculated_at: string;
}

interface BackendListingData {
  items: BackendListingItem[];
}

export interface ListingManagementApiMeta {
  latest_calculated_at: string | null;
  page: number;
  page_size: number;
  total: number;
}

export interface ListingManagementApiResult {
  rows: ListingManagementRow[];
  meta: ListingManagementApiMeta;
}

interface ListingManagementParams {
  storeId?: string;
  pageSize?: number;
}

const numberValue = (value: string | null | undefined) => Number(value ?? 0);

const toDateText = (value: string | null): string => {
  if (!value) return "";
  return value.slice(0, 10);
};

const toCheckedText = (value: string): string => value.replace("T", " ").slice(0, 16);

const toListingRow = (item: BackendListingItem): ListingManagementRow => ({
  id: item.id,
  image: item.picture_url ?? "▤",
  msku: item.msku ?? "-",
  productId: item.item_id,
  store: item.store_name ?? item.store_id,
  owner: item.owner_ref ?? "未分配",
  sku: item.local_sku ?? "-",
  productName: item.local_name ?? item.title ?? "-",
  title: item.title ?? item.local_name ?? "-",
  productType: item.category ?? "待分类",
  listPrice: numberValue(item.strike_price_amount),
  salePrice: numberValue(item.sale_price_amount),
  productStatus: item.disabled_reason ? "停用" : "启用",
  lifecycle: item.lifecycle_status ?? "待计算",
  listedAt: toDateText(item.listing_start_at_utc),
  category: item.category ?? "-",
  wfsAvailableInventory: numberValue(item.wfs_available_quantity),
  inboundInventory: numberValue(item.inbound_quantity),
  sales90Days: numberValue(item.sales_30d),
  adSpend30Days: numberValue(item.ad_spend_30d_amount),
  disabledReason: item.disabled_reason ?? "",
  listingStatus: item.listing_status ?? "待确认",
  buyBoxStatus: item.buybox_status ?? "待确认",
  walmartSeller: item.walmart_seller ?? "待确认",
  resold: item.is_hijacked ? "是" : "否",
  checkedAt: toCheckedText(item.calculated_at),
  rating: numberValue(item.average_rating),
  reviewCount: item.review_count ?? 0,
  brand: item.brand ?? "-",
  tags: item.tags,
  gtin: item.gtin ?? "-",
  productGrade: item.product_grade ?? "未分级",
});

export async function fetchListingManagementRows(
  params: ListingManagementParams = {},
): Promise<ListingManagementApiResult> {
  const search = new URLSearchParams();
  if (params.storeId) search.set("store_id", params.storeId);
  search.set("page", "1");
  search.set("page_size", String(params.pageSize ?? 500));

  const envelope = await backendRequest<BackendListingData, ListingManagementApiMeta>(
    `/api/listings/walmart?${search.toString()}`,
  );

  return {
    rows: envelope.data.items.map(toListingRow),
    meta: envelope.meta,
  };
}
