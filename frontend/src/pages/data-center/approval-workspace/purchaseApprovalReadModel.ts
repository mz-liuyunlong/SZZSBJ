/** Purchase-detail read model: shares existing authorized APIs, never sends a decision. */
import { useQuery } from "@tanstack/react-query";
import type { PurchasePageRead } from "./approvalTypes";
import { backendRequest } from "@/api/backendApi";
import {
  listNewProducts, newProductDetailQueryOptions,
  type Identity, type PageResponse, type NewProductListing,
} from "@/pages/products/new-product/newProductBusinessApi";
import { toPersistedProduct } from "@/pages/products/new-product/newProductRealAdapter";

const EMPTY_IDENTITY: Identity = {source_account_ref:"",store_id:"",item_id:""};

function finiteAmount(value: unknown): number | null {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null;
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function verifiedPurchaseListing(data: PageResponse | undefined, identity: Identity): NewProductListing | null {
  // The list endpoint uses fuzzy search; the full result must prove a unique triple.
  if (!data || !Number.isInteger(data.total) || data.total !== data.items.length) return null;
  const matches = data.items.filter(({listing}) =>
    listing.source_account_ref === identity.source_account_ref &&
    listing.store_id === identity.store_id && listing.item_id === identity.item_id);
  return matches.length === 1 ? matches[0] : null;
}

export function verifiedPurchaseSku(listing: NewProductListing | null, snapshotSku?: string): string | null {
  const current = listing?.listing.local_sku?.trim();
  const snapshot = snapshotSku?.trim();
  if (!current || current === '-' || current === '—') return null;
  if (snapshot && snapshot !== '—' && snapshot !== '-' && snapshot !== current) return null;
  return current;
}

type CostRow = {sku:string|null;purchase_cost_cny:string|null};
export function verifiedUnitCost(rows: CostRow[], total: number | null | undefined, sku: string): number | null {
  if (!Number.isInteger(total) || total !== rows.length) return null;
  const matching = rows.filter(row => row.sku?.trim() === sku);
  const unit = matching.length === 1 ? finiteAmount(matching[0].purchase_cost_cny) : null;
  return unit !== null && unit >= 0 ? unit : null;
}

export function verifiedUnitProfitUsd(value: unknown): number | null {
  const daily = value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string,unknown> : null;
  const totals = daily?.totals && typeof daily.totals === 'object'
    ? daily.totals as Record<string,unknown> : null;
  const units = finiteAmount(totals?.sales_units);
  const profit = finiteAmount(totals?.profit_usd);
  return daily?.status === 'scored' &&
    daily.source === 'new_products_testing_profit_full_history_v2' &&
    daily.policy === 'returns_ignored_samples_excluded_sample_ads_included' &&
    units !== null && units > 0 && profit !== null ? profit / units : null;
}

async function fetchUnitCost(sku: string): Promise<number | null> {
  // Preserve server-side product and purchase-cost field permissions. The raw
  // numeric CNY value avoids parsing rounded display strings or guessing a price.
  const params = new URLSearchParams({sku_batch:sku,page:'1',page_size:'100'});
  const result = await backendRequest<{items:CostRow[]},{total:number|null}>(
    `/api/product-management/skus?${params.toString()}`,
  );
  return verifiedUnitCost(result.data.items,result.meta?.total,sku);
}

export function usePurchaseApprovalReadModel(identity: Identity | undefined, snapshotSku?: string, preloaded?: PurchasePageRead) {
  const key = identity ?? EMPTY_IDENTITY;
  const enabled = !preloaded && Boolean(identity && key.source_account_ref && key.store_id && key.item_id);
  const listing = useQuery({
    queryKey:["purchase-approval-listing",key.source_account_ref,key.store_id,key.item_id],
    queryFn:() => listNewProducts({page:1,pageSize:200,storeId:key.store_id,keyword:key.item_id,searchField:"item_id"}),
    enabled, staleTime:5 * 60_000, gcTime:30 * 60_000, retry:0,
  });
  const detail = useQuery({...newProductDetailQueryOptions(key),enabled,retry:0});
  const matched = enabled && listing.isSuccess ? verifiedPurchaseListing(listing.data,key) : null;
  const sku = verifiedPurchaseSku(matched,snapshotSku);
  const cost = useQuery({
    queryKey:["purchase-approval-unit-cost",key.source_account_ref,key.store_id,key.item_id,sku],
    queryFn:() => fetchUnitCost(sku!),
    enabled:enabled && sku !== null, staleTime:30_000, gcTime:5 * 60_000, retry:0,
  });
  // Query hooks remain unconditional; all three are disabled for a preloaded row.
  // Validate the exact triple again before using the transferred display data.
  if (preloaded) {
    const row=preloaded.listing;
    const valid=identity && row && row.listing.source_account_ref===key.source_account_ref &&
      row.listing.store_id===key.store_id && row.listing.item_id===key.item_id ? row : null;
    const sku=verifiedPurchaseSku(valid,snapshotSku);
    return {
      product:valid ? toPersistedProduct(valid) : null,
      daily:preloaded.daily ?? null,
      loading:false,costLoading:false,profitLoading:false,
      unitProfitUsd:valid ? verifiedUnitProfitUsd(preloaded.daily) : null,
      unitPurchaseCostCny:sku ? finiteAmount(preloaded.unit_purchase_cost_cny) : null,
    };
  }
  const daily = enabled && detail.isSuccess ? detail.data.evaluation_operating_daily : null;
  // Mount the operating panel only when its detail read has settled. A scored
  // payload is preloaded; an unverified payload uses the same warm QueryClient
  // entry so the existing diagnostic-row renderer keeps its semantics.
  const detailSettled = enabled && (detail.isSuccess || detail.isError);
  const product = matched && detailSettled ? toPersistedProduct(matched) : null;
  const validWarm = daily && typeof daily === 'object' && !Array.isArray(daily)
    ? daily as Record<string,unknown> : null;
  const useWarm = validWarm?.status === 'scored' &&
    validWarm.source === 'new_products_testing_profit_full_history_v2' &&
    validWarm.policy === 'returns_ignored_samples_excluded_sample_ads_included' &&
    Array.isArray(validWarm.rows) && Boolean(validWarm.totals) && typeof validWarm.totals === 'object';
  return {
    product,
    // null prevents another GET after a failed or missing detail; undefined
    // lets the existing operating component consume the already-cached evidence.
    daily: useWarm ? daily : detail.isSuccess && daily != null ? undefined : null,
    loading: enabled && (listing.isPending || detail.isPending),
    costLoading: enabled && (listing.isPending || (sku !== null && cost.isPending)),
    profitLoading: enabled && detail.isPending,
    unitProfitUsd: enabled ? verifiedUnitProfitUsd(daily) : null,
    unitPurchaseCostCny: enabled && sku && cost.isSuccess ? cost.data : null,
  };
}
