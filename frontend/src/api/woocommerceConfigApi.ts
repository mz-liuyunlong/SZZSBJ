import { backendRequest } from "@/api/backendApi";

export interface WooCommerceStore {
  id: string;
  name: string;
  store_url: string;
  enabled: boolean;
  consumer_key_configured: boolean;
  consumer_secret_configured: boolean;
  last_test_at: string | null;
  last_test_ok: boolean | null;
  last_test_code: string | null;
  updated_at: string;
}

export interface WooCommerceStoreWrite {
  name: string;
  store_url: string;
  consumer_key?: string;
  consumer_secret?: string;
  enabled: boolean;
}

export interface WooCommerceTestResult {
  ok: boolean;
  code: string;
}

const base = "/api/system-config/woocommerce/stores";

export async function listWooCommerceStores(): Promise<WooCommerceStore[]> {
  return (await backendRequest<WooCommerceStore[]>(base)).data;
}

export async function createWooCommerceStore(
  payload: WooCommerceStoreWrite,
): Promise<WooCommerceStore> {
  return (await backendRequest<WooCommerceStore>(base, {
    method: "POST",
    body: JSON.stringify(payload),
  })).data;
}

export async function updateWooCommerceStore(
  storeId: string,
  payload: WooCommerceStoreWrite,
): Promise<WooCommerceStore> {
  return (await backendRequest<WooCommerceStore>(`${base}/${encodeURIComponent(storeId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })).data;
}

export async function testWooCommerceStore(
  storeId: string,
): Promise<WooCommerceTestResult> {
  return (await backendRequest<WooCommerceTestResult>(
    `${base}/${encodeURIComponent(storeId)}/test`,
    { method: "POST" },
  )).data;
}
