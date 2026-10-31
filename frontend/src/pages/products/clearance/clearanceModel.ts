/** WFS clearance demo domain: pure, deterministic and free of production side effects. */
export const CLEARANCE_STORAGE_KEY = "wfs_clearance_center_v4_20261024";
export type PeriodDays = 7 | 14 | 30;
export type RiskLevel = "high" | "medium" | "low";
export type TaskStatus = "pending" | "supplement" | "ready" | "running" | "paused" | "done" | "rejected" | "cancelled";
export type ClearanceSource = "auto" | "manual";
export interface SalesPeriod {
  units: number;
  revenue: number;
  ads: number;
  adRate: number | null;
  profit: number;
  margin: number | null;
}
export interface ClearanceProduct {
  id: string;
  sku: string;
  msku: string;
  item: string;
  name: string;
  store: string;
  owner: string;
  avail: number;
  res: number;
  bad: number;
  inbound: number;
  age: number;
  listingDays: number;
  ageLots: { ageDays: number; qty: number }[];
  returns: number;
  rating: number;
  reviewCount: number;
  price: number;
  cost: number;
  per: Record<PeriodDays, SalesPeriod>;
}
export interface ClearanceRules {
  highCoverage: number;
  mediumCoverage: number;
  assistCoverage: number;
  mediumAge: number;
  agedLotDays: number;
  agedLotMin: number;
  zeroLookback: PeriodDays;
  minListingDays: number;
  minBusinessSignals: number;
  salesDropPercent: number;
  adRateIncrease: number;
  returnRate: number;
  ratingThreshold: number;
  enableCoverage: boolean;
  enableZero: boolean;
  enableAged: boolean;
  enableAverageAge: boolean;
  enableAssisted: boolean;
  enableProfit: boolean;
  enableDecline: boolean;
  enableAd: boolean;
  enableReturns: boolean;
  enableRating: boolean;
}
export const DEFAULT_RULES: ClearanceRules = {
  highCoverage:180,mediumCoverage:90,assistCoverage:60,mediumAge:180,
  agedLotDays:365,agedLotMin:1,zeroLookback:30,minListingDays:30,
  minBusinessSignals:1,salesDropPercent:40,adRateIncrease:5,returnRate:8,ratingThreshold:3.8,
  enableCoverage:true,enableZero:true,enableAged:true,enableAverageAge:true,
  enableAssisted:true,enableProfit:true,enableDecline:true,enableAd:true,
  enableReturns:true,enableRating:true,
};
type SourceRow = Pick<ClearanceProduct,"id"|"sku"|"msku"|"item"|"name"|"store"|"owner"|"avail"|"res"|"bad"|"inbound"|"age"|"price"|"cost"> & {s7:number;s30:number};
const source: SourceRow[] = [
 {id:"WFS-101",sku:"DEMO-SKU-101",msku:"DEMO-MSKU-101A",item:"DEMO-ITEM-1001",name:"抽屉分格收纳盒",store:"美区一店",owner:"刘运营",avail:860,res:34,bad:6,inbound:0,age:213,s7:2,s30:14,price:15.99,cost:8.6},
 {id:"WFS-102",sku:"DEMO-SKU-102",msku:"DEMO-MSKU-102B",item:"DEMO-ITEM-1002",name:"厨房密封收纳罐",store:"美区一店",owner:"刘运营",avail:540,res:16,bad:8,inbound:120,age:184,s7:5,s30:33,price:19.99,cost:10.3},
 {id:"WFS-103",sku:"DEMO-SKU-103",msku:"DEMO-MSKU-103C",item:"DEMO-ITEM-1003",name:"办公封箱胶带套装",store:"美区二店",owner:"陈运营",avail:920,res:21,bad:0,inbound:0,age:118,s7:9,s30:51,price:12.49,cost:6.2},
 {id:"WFS-104",sku:"DEMO-SKU-104",msku:"DEMO-MSKU-104D",item:"DEMO-ITEM-1004",name:"可叠加桌面收纳架",store:"美区二店",owner:"陈运营",avail:680,res:45,bad:11,inbound:0,age:241,s7:0,s30:5,price:27.99,cost:14.8},
 {id:"WFS-105",sku:"DEMO-SKU-105",msku:"DEMO-MSKU-105E",item:"DEMO-ITEM-1005",name:"厨房一次性手套",store:"美区三店",owner:"吴运营",avail:360,res:13,bad:2,inbound:0,age:85,s7:25,s30:123,price:9.99,cost:4.1},
 {id:"WFS-106",sku:"DEMO-SKU-106",msku:"DEMO-MSKU-106F",item:"DEMO-ITEM-1006",name:"布艺衣柜分隔袋",store:"美区一店",owner:"刘运营",avail:310,res:10,bad:3,inbound:0,age:153,s7:4,s30:18,price:18.99,cost:9.8},
 {id:"WFS-107",sku:"DEMO-SKU-107",msku:"DEMO-MSKU-107G",item:"DEMO-ITEM-1007",name:"洗碗海绵补充装",store:"美区二店",owner:"陈运营",avail:560,res:18,bad:0,inbound:0,age:92,s7:37,s30:128,price:11.49,cost:5.1},
 {id:"WFS-108",sku:"DEMO-SKU-108",msku:"DEMO-MSKU-108H",item:"DEMO-ITEM-1008",name:"浴室置物挂钩套装",store:"美区三店",owner:"吴运营",avail:475,res:8,bad:14,inbound:0,age:198,s7:3,s30:9,price:14.99,cost:7.5},
 {id:"WFS-109",sku:"DEMO-SKU-109",msku:"DEMO-MSKU-109J",item:"DEMO-ITEM-1009",name:"桌面线材收纳夹",store:"美区三店",owner:"吴运营",avail:150,res:9,bad:0,inbound:0,age:133,s7:12,s30:37,price:8.99,cost:3.7},
 {id:"WFS-110",sku:"DEMO-SKU-110",msku:"DEMO-MSKU-110K",item:"DEMO-ITEM-1010",name:"保鲜袋组合装",store:"美区一店",owner:"刘运营",avail:650,res:18,bad:0,inbound:0,age:62,s7:94,s30:374,price:10.99,cost:4.5},
 {id:"WFS-111",sku:"DEMO-SKU-111",msku:"DEMO-MSKU-111L",item:"DEMO-ITEM-1011",name:"可折叠书本支架",store:"美区二店",owner:"陈运营",avail:410,res:22,bad:7,inbound:0,age:177,s7:3,s30:13,price:22.99,cost:11.9},
 {id:"WFS-112",sku:"DEMO-SKU-112",msku:"DEMO-MSKU-112M",item:"DEMO-ITEM-1012",name:"厨房防滑垫",store:"美区三店",owner:"吴运营",avail:170,res:14,bad:1,inbound:0,age:101,s7:8,s30:34,price:13.49,cost:6.6},
 {id:"WFS-113",sku:"DEMO-SKU-113",msku:"DEMO-MSKU-113N",item:"DEMO-ITEM-1013",name:"文件夹标签套装",store:"美区一店",owner:"刘运营",avail:390,res:4,bad:0,inbound:0,age:35,s7:70,s30:232,price:8.99,cost:3.4},
 {id:"WFS-114",sku:"DEMO-SKU-114",msku:"DEMO-MSKU-114P",item:"DEMO-ITEM-1014",name:"洗衣袋三件套",store:"美区二店",owner:"陈运营",avail:250,res:5,bad:2,inbound:0,age:147,s7:2,s30:7,price:17.99,cost:8.8},
];
export const CLEARANCE_PRODUCTS: ClearanceProduct[] = source.map((row,i)=>{
  const prev7 = Math.round((row.s30-row.s7) * (.22+(i%4)*.06));
  const s14 = Math.min(row.s30,row.s7+Math.max(0,prev7));
  const age365 = row.age>=210 ? Math.max(4,Math.round(row.avail*.065)) : 0;
  const returns = row.s30>=30
    ? Math.round(row.s30*(i%4===1?.10:i%4===0?.045:.025))
    : Math.max(0,Math.round(row.s30*.06));
  const period = (days:PeriodDays,units:number):SalesPeriod=>{
    const discount=1-(i%3)*.024;
    const revenue=Number((units*row.price*discount).toFixed(2));
    const rate=days===7?.13+(i%4)*.043:days===14?.12+(i%4)*.035:.10+(i%4)*.024;
    const ads=Number((revenue*rate+(units===0?4.5:0)).toFixed(2));
    const profit=Number((revenue-units*row.cost-revenue*.15-ads-units*.18).toFixed(2));
    return {units,revenue,ads,profit,adRate:revenue>0?ads/revenue*100:null,margin:revenue>0?profit/revenue*100:null};
  };
  return {
    ...row,listingDays:row.age+35,
    ageLots:age365?[{ageDays:375+(i%5)*28,qty:age365}]:[],
    returns,rating:[4.2,4.1,4.4,3.5,4.6,3.8,4.7,3.6,4.3,4.8,4.0,3.9,4.5,3.7][i],
    reviewCount:[113,58,77,24,92,32,128,39,23,304,22,45,173,18][i],
    per:{7:period(7,row.s7),14:period(14,s14),30:period(30,row.s30)},
  };
});
export const REASONS = ["库存滞销","WFS库龄过高","季节性清仓","产品升级换代","准备停售","质量问题","经营策略调整","其他原因"];
export const METHODS = ["降价","促销","广告调整","WFS移除","弃置"];
export const STATUS_NAMES: Record<TaskStatus,string> = {
  pending:"待审批",supplement:"待补资料",ready:"待执行",running:"执行中",
  paused:"已暂停",done:"已完成",rejected:"已驳回",cancelled:"已撤回",
};
export const RISK_NAMES: Record<RiskLevel,string> = {high:"高风险",medium:"中风险",low:"低风险"};
export interface RiskEvaluation {level:RiskLevel;auto:boolean;reasons:string[];business:string[]}
export function coverage(x:ClearanceProduct):number|null{
  const units=x.per[30].units;
  return units>0?Math.ceil(x.avail/(units/30)):null;
}
export function businessSignals(x:ClearanceProduct,r:ClearanceRules):string[]{
  const p7=x.per[7],p14=x.per[14],p30=x.per[30],prev7=p14.units-p7.units,signals:string[]=[];
  if(r.enableProfit&&p7.profit<0&&p14.profit<0&&p14.units>=3)signals.push("近7天与14天持续亏损");
  if(r.enableDecline&&prev7>=10&&p7.units<=prev7*(1-r.salesDropPercent/100)&&prev7-p7.units>=5)signals.push("近7天销量较前7天下滑≥"+r.salesDropPercent+"%");
  if(r.enableAd&&p7.adRate!==null&&p30.adRate!==null&&p7.adRate-p30.adRate>=r.adRateIncrease&&p7.profit<0)signals.push("近期广告占比上升≥"+r.adRateIncrease+"个百分点且亏损");
  if(r.enableReturns&&x.returns>=5&&p30.units>=30&&x.returns/p30.units*100>=r.returnRate)signals.push("30天退货率≥"+r.returnRate+"%");
  if(r.enableRating&&x.rating<r.ratingThreshold&&x.reviewCount>=10)signals.push("商品评分低于"+r.ratingThreshold);
  return signals;
}
export function evaluateProduct(x:ClearanceProduct,r:ClearanceRules):RiskEvaluation{
  const cov=coverage(x),business=businessSignals(x,r),reasons:string[]=[];
  let level:RiskLevel="low";
  if(x.avail<=0)return {level,auto:false,reasons:["无WFS可售库存"],business};
  const aged=x.ageLots.filter(l=>l.ageDays>r.agedLotDays).reduce((sum,l)=>sum+l.qty,0);
  if(r.enableAged&&aged>=r.agedLotMin){level="high";reasons.push("超过"+r.agedLotDays+"天的库龄批次 "+aged+" 件");}
  const zero=x.per[r.zeroLookback];
  if(r.enableZero&&zero&&zero.units===0&&x.listingDays>=r.minListingDays){level="high";reasons.push("在售≥"+r.minListingDays+"天且近"+r.zeroLookback+"天零销量");}
  if(r.enableCoverage&&cov!==null&&cov>=r.highCoverage){level="high";reasons.push("预计售罄 "+cov+" 天（≥"+r.highCoverage+"天）");}
  if(level!=="high"&&((r.enableCoverage&&cov!==null&&cov>=r.mediumCoverage)||(r.enableAverageAge&&x.age>=r.mediumAge))){
    level="medium";
    if(r.enableCoverage&&cov!==null&&cov>=r.mediumCoverage)reasons.push("预计售罄 "+cov+" 天（≥"+r.mediumCoverage+"天）");
    if(r.enableAverageAge&&x.age>=r.mediumAge)reasons.push("平均库龄 "+x.age+" 天（≥"+r.mediumAge+"天）");
  }
  if(level==="low"&&r.enableAssisted&&cov!==null&&cov>=r.assistCoverage&&business.length>=r.minBusinessSignals){
    level="medium";reasons.push("预计售罄≥"+r.assistCoverage+"天且存在≥"+r.minBusinessSignals+"项经营异常");
  }
  if(level==="low")reasons.push("暂未达到自动清货准入条件");
  return {level,auto:level!=="low",reasons,business};
}
export function validateRules(r:ClearanceRules):string{
  const keys:(keyof ClearanceRules)[]=["highCoverage","mediumCoverage","assistCoverage","mediumAge","agedLotDays","agedLotMin","minListingDays","minBusinessSignals","salesDropPercent","adRateIncrease","returnRate","ratingThreshold"];
  for(const key of keys) if(typeof r[key]!=="number"||!Number.isFinite(r[key])||Number(r[key])<0)return "请检查规则字段："+key+"，必须为非负有效数字";
  if(!Number.isInteger(r.highCoverage)||!Number.isInteger(r.mediumCoverage)||!Number.isInteger(r.assistCoverage)||r.assistCoverage>=r.mediumCoverage||r.mediumCoverage>=r.highCoverage)return "售罄阈值必须为整数，且：经营辅助准入 ＜ 中风险 ＜ 高风险";
  if(![7,14,30].includes(r.zeroLookback))return "零销量观察窗口只能为7、14、30天";
  if(r.salesDropPercent>100||r.returnRate>100||r.adRateIncrease>100||r.ratingThreshold>5||r.ratingThreshold<1)return "百分比范围为0～100，评分阈值为1～5";
  if(r.agedLotMin<1||r.minBusinessSignals<1||r.minBusinessSignals>5||!Number.isInteger(r.agedLotMin)||!Number.isInteger(r.minBusinessSignals))return "超龄库存件数与辅助信号数量必须为正整数";
  if(r.highCoverage>3650||r.mediumAge>3650||r.agedLotDays>3650||r.minListingDays>3650)return "天数阈值不能超过3650天";
  return "";
}
export interface ClearanceTaskLine {id:string;qty:number;sold:number;removed:number;disposed:number}
export interface TaskHistory {at:string;who:string;text:string}
export interface ClearanceTask {
  id:string; lines:ClearanceTaskLine[]; status:TaskStatus;
  reason:string;methods:string[];owner:string;requester:string;approver:string;
  date:string;due:string;submitted:string;remark:string;source:ClearanceSource;
  history:TaskHistory[];version:number;ruleVersion:number;riskAtSubmission:RiskLevel;
}
const productById=new Map(CLEARANCE_PRODUCTS.map(x=>[x.id,x]));
export const findProduct=(id:string):ClearanceProduct|undefined=>productById.get(id);
export const activeTaskFor=(tasks:ClearanceTask[],id:string)=>tasks.find(t=>t.lines.some(l=>l.id===id)&&["pending","supplement","ready","running","paused"].includes(t.status));
export const latestTaskFor=(tasks:ClearanceTask[],id:string)=>tasks.filter(t=>t.lines.some(l=>l.id===id)).sort((a,b)=>b.submitted.localeCompare(a.submitted))[0];
export const taskQty=(t:ClearanceTask)=>t.lines.reduce((v,l)=>v+l.qty,0);
export const taskSold=(t:ClearanceTask)=>t.lines.reduce((v,l)=>v+l.sold,0);
export const taskRemoved=(t:ClearanceTask)=>t.lines.reduce((v,l)=>v+l.removed+l.disposed,0);
export const taskProcessed=(t:ClearanceTask)=>taskSold(t)+taskRemoved(t);
export const taskIsComplete=(t:ClearanceTask)=>taskQty(t)>0&&taskProcessed(t)===taskQty(t);
/** Round down for display; never round an incomplete task up to 100%. */
export const taskProgress=(t:ClearanceTask)=>Math.floor(taskProcessed(t)*100/Math.max(1,taskQty(t)));
export const taskCost=(t:ClearanceTask)=>t.lines.reduce((v,l)=>v+l.qty*(findProduct(l.id)?.cost??0),0);
export const taskStore=(t:ClearanceTask)=>findProduct(t.lines[0]?.id)?.store??"";
export const taskRisk=(t:ClearanceTask,r:ClearanceRules):RiskLevel=>{
 const levels=t.lines.map(l=>findProduct(l.id)).filter((x):x is ClearanceProduct=>Boolean(x)).map(x=>evaluateProduct(x,r).level);
 return levels.includes("high")?"high":levels.includes("medium")?"medium":"low";
};
function seedTask(id:string,ids:string[],status:TaskStatus,reason:string,methods:string[],owner:string,qtys:number[],kind:ClearanceSource,remark:string):ClearanceTask{
  const lines=ids.map((pid,i)=>({id:pid,qty:qtys[i],sold:0,removed:0,disposed:0}));
  if(status==="running"){lines[0].sold=Math.min(65,lines[0].qty);lines[0].removed=Math.min(15,lines[0].qty-lines[0].sold);}
  if(status==="done")lines.forEach(l=>{l.sold=l.qty;});
  const result:ClearanceTask={id,lines,status,reason,methods,owner,requester:owner,approver:"李主管",date:"2026-10-18",due:"2026-11-30",submitted:"2026-10-18 14:28",remark,source:kind,version:1,ruleVersion:1,riskAtSubmission:"low",history:[{at:"2026-10-18 14:28",who:owner,text:"提交清货申请至统一审批工作台"}]};
  if(status!=="pending")result.history.push({at:"2026-10-19 11:10",who:"李主管",text:status==="rejected"?"审批驳回":status==="supplement"?"要求补充资料":"审批通过；允许进入清货执行阶段"});
  result.riskAtSubmission=taskRisk(result,DEFAULT_RULES);
  return result;
}
export function seedTasks():ClearanceTask[]{
 return [
  seedTask("CH-1024-006",["WFS-106","WFS-102"],"pending","库存滞销",["促销","广告调整"],"刘运营",[180,200],"auto","WFS 库存占用较高，近期日均销量持续下降，请批准分阶段促销，优先降低库存成本。"),
  seedTask("CH-1024-005",["WFS-110"],"pending","产品升级换代",["降价","促销"],"刘运营",[220],"manual","新款即将替换旧款，需要提前处理现有 WFS 库存，避免新旧型号并行带来额外仓储成本。"),
  seedTask("CH-1023-004",["WFS-111"],"ready","WFS库龄过高",["降价","促销"],"陈运营",[280],"auto","售罄周期过长，申请调整促销策略并逐步消化老库存。"),
  seedTask("CH-1022-003",["WFS-108"],"running","库存滞销",["促销","WFS移除"],"吴运营",[300],"auto","库存周转异常，已获审批，先执行促销并观察销售结果。"),
  seedTask("CH-1020-002",["WFS-103"],"done","库存滞销",["广告调整","促销"],"陈运营",[180],"auto","已完成此前清货目标，归档相关过程数据和处理记录。"),
  seedTask("CH-1019-001",["WFS-114"],"rejected","WFS库龄过高",["弃置"],"陈运营",[180],"auto","尝试直接弃置库存；领导要求先评估降价促销方案。"),
 ];
}
export interface RulesHistory {version:number;actor:string;at:string;summary:string}
export interface StoredClearance {
  tasks:ClearanceTask[];manual:string[];ignored:string[];
  rules:ClearanceRules;ruleVersion:number;ruleHistory:RulesHistory[];
}
export function initialClearance():StoredClearance{
  const defaults:StoredClearance={tasks:seedTasks(),manual:["WFS-110"],ignored:[],rules:{...DEFAULT_RULES},ruleVersion:1,ruleHistory:[]};
  if(typeof window==="undefined")return defaults;
  try{
    const raw=localStorage.getItem(CLEARANCE_STORAGE_KEY);
    if(!raw)return defaults;
    const stored:Partial<StoredClearance>=JSON.parse(raw) as Partial<StoredClearance>;
    const rules={...DEFAULT_RULES,...stored.rules};
    return {
      tasks:Array.isArray(stored.tasks)?stored.tasks.map(t=>({...t,ruleVersion:t.ruleVersion??1,riskAtSubmission:t.riskAtSubmission??"low"})):defaults.tasks,
      manual:Array.isArray(stored.manual)?stored.manual:defaults.manual,
      ignored:Array.isArray(stored.ignored)?stored.ignored:defaults.ignored,
      rules:validateRules(rules)?defaults.rules:rules,
      ruleVersion:Math.max(1,Number(stored.ruleVersion)||1),
      ruleHistory:Array.isArray(stored.ruleHistory)?stored.ruleHistory:[],
    };
  }catch{return defaults;}
}
export function persistClearance(data:StoredClearance):void{
 try{if(typeof window!=="undefined")localStorage.setItem(CLEARANCE_STORAGE_KEY,JSON.stringify(data));}catch{/* Demo works without storage. */}
}
/** China business time for mock audit and task IDs (not a backend timestamp). */
export function chinaNow(now:Date=new Date()):string{
 const parts=new Intl.DateTimeFormat("en-GB",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(now);
 const get=(type:string)=>parts.find(p=>p.type===type)?.value??"";
 return get("year")+"-"+get("month")+"-"+get("day")+" "+get("hour")+":"+get("minute");
}
export function nextClearanceTaskId(tasks:ClearanceTask[],at:string):string{
 const day=at.slice(5,10).replace("-","");
 const prefix="CH-"+day+"-";
 const last=tasks.reduce((max,t)=>{
   const number=t.id.startsWith(prefix)?Number(t.id.slice(prefix.length)):0;
   return Number.isInteger(number)?Math.max(max,number):max;
 },0);
 return prefix+String(last+1).padStart(3,"0");
}
export function chinaToday():string{
 const parts=new Intl.DateTimeFormat("en-US",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
 const get=(type:string)=>parts.find(p=>p.type===type)?.value??"";
 return get("year")+"-"+get("month")+"-"+get("day");
}
export function csvCell(value:unknown):string{
 let text=String(value??"");
 if(/^[=+\-@]/.test(text))text="'"+text;
 return '"'+text.replace(/"/g,'""')+'"';
}
export function toCsv(headers:string[],rows:unknown[][]):string{
 return "\ufeff"+[headers,...rows].map(row=>row.map(csvCell).join(",")).join("\r\n");
}
