import { Popover } from "antd";
import type { LinkedWoo } from "./useWooListingLinks";

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
