import { useQuery } from "@tanstack/react-query";
import { backendRequest } from "@/api/backendApi";

export type WooListingIdentity = { source_account_ref: string; store_id: string; item_id: string };
export type LinkedWoo = WooListingIdentity & { woo_product_id: string; store_name: string; url: string | null; price: string | null; currency: string | null; publish_status: string | null; stock_status: string | null; last_synced_at: string };
export const wooIdentity = (account?: string, store?: string, item?: string): WooListingIdentity | undefined => account && store && item ? {source_account_ref:account,store_id:store,item_id:item} : undefined;
const key = (i: WooListingIdentity) => JSON.stringify([i.source_account_ref, i.store_id, i.item_id]);

export function useWooListingLinks(identities: readonly (WooListingIdentity | undefined)[]) {
  const distinct = new Map<string, WooListingIdentity>();
  for (const i of identities) if (i?.source_account_ref && i.store_id && i.item_id) distinct.set(key(i), i);
  const keys = [...distinct.keys()].sort();
  const query = useQuery({
    queryKey: ["woo-listing-links", keys],
    enabled: keys.length > 0,
    staleTime: 60000,
    retry: false,
    queryFn: async ({signal}) => {
      const grouped = new Map<string, LinkedWoo[]>();
      for (let offset=0; offset<keys.length; offset+=500) {
        const response = await backendRequest<LinkedWoo[]>("/api/woocommerce/products/listing-links", {method:"POST",body:JSON.stringify({identities: keys.slice(offset,offset+500).map(k=>distinct.get(k))}),signal});
        for (const r of response.data) { const k=key(r); grouped.set(k,[...(grouped.get(k) ?? []),r]); }
      }
      return grouped;
    },
  });
  return (identity?: WooListingIdentity) => identity ? query.data?.get(key(identity)) : undefined;
}
