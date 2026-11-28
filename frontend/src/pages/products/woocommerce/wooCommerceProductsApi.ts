import { backendRequest } from "@/api/backendApi";
import type { WooProductRow } from "./wooCommerceProductTypes";

export type WooOption = { value: string; label: string };
export type WooStoreOption = WooOption & { brands: WooOption[]; categories: WooOption[] };
export type WalmartStoreOption = { account: string; storeId: string; label: string };
export type BrandRule = { source_brand: string; target_store_id: string; target_brand_id: string; target_category_id: string; enabled: boolean };
export type SubmissionRule = { source_account_ref: string; source_store_id: string; submission_store_id: string };
export type Rules = {
  version: number; auto_publish_enabled: boolean; listing_status: "active" | "review";
  price_mode: "original" | "fixed" | "percent"; price_markup: string;
  stock_quantity: number | null; retry_enabled: boolean; retry_limit: number;
  submission_interval_days: number; mappings: BrandRule[]; submission_stores: SubmissionRule[];
};
export type RulesData = { rules: Rules; stores: WooStoreOption[]; walmart_stores: WalmartStoreOption[] };
const base = "/api/woocommerce/products";
export type WooCatalog = { items: WooProductRow[]; total: number; summary: Record<string, number>; stores: WooOption[]; brands: string[] };
export async function fetchWooProducts(query: URLSearchParams, signal?: AbortSignal) {
  return (await backendRequest<WooCatalog>(`${base}?${query.toString()}`, { signal })).data;
}
export async function fetchWooRules(signal?: AbortSignal) {
  return (await backendRequest<RulesData>(`${base}/rules`, { signal })).data;
}
export async function saveWooRules(rules: Rules) {
  return (await backendRequest<RulesData>(`${base}/rules`, { method: "PUT", body: JSON.stringify(rules) })).data;
}
