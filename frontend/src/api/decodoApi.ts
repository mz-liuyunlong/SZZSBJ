import { backendRequest } from "@/api/backendApi";

export interface DecodoConfig {
  mode?: "database" | "local_test";
  configured: boolean;
  enabled: boolean;
  us_zip: string;
  updated_at: string | null;
  updated_by: string | null;
}

export interface DecodoUsageDay {
  date: string;
  amazon_requests: number;
  walmart_requests: number;
  total: number;
  success: number;
  failed: number;
  pending: number;
}

export interface DecodoUsage {
  timezone: string;
  today: string;
  days: DecodoUsageDay[];
}

export interface WalmartFacts {
  snapshot_id?: string | null;
  gtin?: string | null;
  seller_name?: string | null;
  item_id: string;
  sku_id: string;
  title: string;
  brand: string | null;
  description: string | null;
  category_path: string[];
  attributes: Record<string, string>;
  main_image: string | null;
  gallery_images: string[];
  url: string | null;
  fetched_at: string;
  verified: boolean;
}

export interface AmazonEvidence {
  snapshot_id?: string | null;
  asin: string;
  title: string;
  brand: string | null;
  manufacturer: string | null;
  bullet_points: string[];
  description: string | null;
  category_path: string[];
  attributes: Record<string, string>;
  main_image: string | null;
  gallery_images: string[];
  url: string | null;
  fetched_at: string;
  verified: boolean;
}

export interface AmazonResearchResult {
  items: AmazonEvidence[];
  failures: string[];
  requested: number;
  completed: number;
}

export async function fetchDecodoConfig(): Promise<DecodoConfig> {
  return (await backendRequest<DecodoConfig>("/api/business-rules/decodo")).data;
}

export async function updateDecodoConfig(input: {authorization?: string; us_zip: string; enabled: boolean}): Promise<DecodoConfig> {
  return (await backendRequest<DecodoConfig>("/api/business-rules/decodo", {
    method: "PUT", body: JSON.stringify(input),
  })).data;
}

export async function fetchDecodoUsage(days = 7): Promise<DecodoUsage> {
  return (await backendRequest<DecodoUsage>(`/api/business-rules/decodo/usage?days=${days}`)).data;
}

export async function confirmWalmartFacts(skuId: string, itemId: string): Promise<WalmartFacts> {
  return (await backendRequest<WalmartFacts>("/api/keyword-planning/products/confirm", {
    method: "POST", body: JSON.stringify({sku_id:skuId,item_id:itemId}),
  })).data;
}

export async function researchAmazonAsins(asins: string[], skuId: string): Promise<AmazonResearchResult> {
  return (await backendRequest<AmazonResearchResult>("/api/keyword-planning/amazon/research", {
    method: "POST", body: JSON.stringify({asins,sku_id:skuId}),
  })).data;
}
