/** Mock fixtures for local acceptance; no network or production side effects. */
import type { ProductSample, ApprovalState, TrackState } from "./newProductModel";
const row = (sku: string, name: string, category: string, developer: string, operator: string,
  listedAt: string, market: number | null, system: ProductSample["system"],
  roi: number, demand: number, approval: ApprovalState, tracking: TrackState,
  sales30: number, sales60: number, sales90: number, approvedQty: number | null,
  progress: string, requestQty: number | null = null): ProductSample => ({
  id: sku, sku, itemId: "18420" + sku.replace(/\D/g, "").padStart(7, "0"),
  name, category, developer, operator, listedAt, market,
  marketReason: market === null ? "" : "竞品价格与 Review 分布已人工核对；有一定差异化空间。",
  system, overrides: {}, roi, margin: roi < .7 ? 15.3 : roi * 15 + 8,
  acos: Math.max(12, 42 - system.ads * 3), clicks: Math.round(20 + system.order * 17),
  orders: Math.round(system.order * 2.2), sales30, sales60, sales90,
  adSpend: 30 + system.ads * 12, inventory: approvedQty === null ? 0 : Math.max(0, approvedQty - sales90),
  periodMetrics: Object.fromEntries(([30,60,90] as const).map((days,i)=>{
    const sales=[sales30,sales60,sales90][i], clicks=Math.round((24+system.order*17)*days/30),
    orders=Math.round((6+system.order*2)*days/30),adSpend=Math.round((32+system.ads*12)*days/30*100)/100,
    acos=Math.max(12,42-system.ads*3),margin=roi<.7?15.3:roi*15+8;
    return [String(days),{clicks,orders,sales,adSpend,acos,margin,profit:Math.round(sales*margin)/100,dataAvailable:approval==="approved"||tracking==="打品失败"}];
  })) as ProductSample["periodMetrics"],
  unitCost: roi < .7 ? 9 : 6.8, demand, actualPurchaseQty:approvedQty, approval,
  requestQty, requestReason: requestQty === null ? "" : "结合实际出单表现，申请调整采购数量。",
  approvedQty, arrivedAt: ["观察中", "打品成功", "打品失败"].includes(tracking) ? "2026-08-10" : null,
  sellableAt: ["观察中", "打品成功", "打品失败"].includes(tracking) ? "2026-08-12" : null,
  tracking, progress, failureReason: tracking === "打品失败" ? "广告转化不足、库存消化慢" : "",
});
export const mockProducts: ProductSample[] = [
  row("YC00738","0.6×3m 双层隔热膜","家居耗材","王宁","陈佳","2026-09-21",null,{order:8,ads:10,profit:3,trust:6},.5,280,"none","未进入打品池",0,0,0,null,"待测评"),
  row("YC00752","抽屉分隔收纳盒","收纳用品","林晓","王宁","2026-09-23",null,{order:9,ads:8,profit:8,trust:9},1.32,460,"none","未进入打品池",0,0,0,null,"待测评"),
  row("YC00761","厨房保鲜分装盒","厨房用品","赵敏","李倩","2026-10-17",null,{order:7,ads:7,profit:7,trust:6},.96,250,"none","未进入打品池",0,0,0,null,"测评中"),
  row("YC00806","厨房水槽滤网套装","厨房用品","王宁","李倩","2026-09-15",8,{order:8,ads:7,profit:7,trust:8},1.16,330,"none","未进入打品池",0,0,0,null,"待运营确认"),
  row("YC00831","办公打包标签纸","办公打包","赵敏","陈佳","2026-09-01",7,{order:7,ads:6,profit:8,trust:8},1.25,220,"pending","等待到货",0,0,0,null,"待领导审核",260),
  row("YC00872","硅胶防滑垫","厨房用品","陈佳","李倩","2026-08-24",9,{order:9,ads:8,profit:9,trust:9},1.42,520,"approved","观察中",162,283,370,500,"采购到货"),
  row("YC00901","真空压缩收纳袋","收纳用品","林晓","王宁","2026-07-28",8,{order:8,ads:7,profit:7,trust:8},1.08,360,"approved","打品成功",245,422,508,550,"采购到货"),
  row("YC00914","厨房保鲜袋收纳架","厨房用品","赵敏","陈佳","2026-07-31",6,{order:5,ads:4,profit:6,trust:7},.72,180,"approved","打品失败",39,71,86,350,"打品复盘"),
  row("YC00930","可重复使用打包袋","办公打包","王宁","李倩","2026-08-15",8,{order:8,ads:8,profit:7,trust:8},1.18,310,"approved","观察中",128,190,250,310,"采购到货"),
  row("YC00955","多用途挂钩组合","家居耗材","林晓","陈佳","2026-08-05",9,{order:9,ads:9,profit:8,trust:9},1.55,560,"approved","打品成功",260,480,620,650,"采购到货"),
  row("YC01015","办公桌理线夹","办公打包","陈佳","王宁","2026-08-02",5,{order:4,ads:3,profit:5,trust:6},.67,180,"none","未进入打品池",0,0,0,null,"停止推进"),
  row("YC01067","可折叠收纳篮","收纳用品","王宁","陈佳","2026-09-18",8,{order:9,ads:7,profit:9,trust:8},1.4,420,"pending","等待到货",0,0,0,null,"待领导审核",460),
];
