import { useQuery } from "@tanstack/react-query";
import { Popover } from "antd";
import { backendRequest } from "@/api/backendApi";

export type WooListingIdentity = { source_account_ref: string; store_id: string; item_id: string };
type LinkedWoo = WooListingIdentity & { woo_product_id: string; store_name: string; url: string | null; price: string | null; currency: string | null; publish_status: string | null; stock_status: string | null; last_synced_at: string };
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

function safeLink(url: string | null): string | undefined {
  if (!url) return undefined;
  try { const u = new URL(url); if (["https:","http:"].includes(u.protocol) && !u.username && !u.password) return u.href; } catch { /* Do not link an invalid URL. */ }
  return undefined;
}
export function WooListingLinkBadge({links}: {links: LinkedWoo[] | undefined}) {
  if (!links?.length) return null;
  return <Popover title="已关联独立站商品" content={<div style={{maxWidth:340}}>{links.map((r,i)=>{
    const href=safeLink(r.url);
    return <div key={`${r.woo_product_id}:${r.store_name}:${i}`} style={{marginBottom:4}}>
      <div>{href ? <a href={href} target="_blank" rel="noopener noreferrer">{r.store_name} · {r.woo_product_id}</a> : <span>{r.store_name} · {r.woo_product_id}</span>}</div>
      <div>{r.price!==null && r.currency ? `${r.currency} ${r.price}` : "价格未知"} · {r.publish_status==="publish"?"已发布":r.publish_status??"状态未知"} · {r.stock_status==="instock"?"有货":r.stock_status??"库存未知"}</div>
      <div style={{color:"#888",fontSize:12}}>最近同步 {r.last_synced_at.slice(0,10)}</div>
    </div>;
  })}</div>}><span style={{color:"#1677ff",cursor:"help",fontSize:12}}>独立站 {links.length}</span></Popover>;
}
