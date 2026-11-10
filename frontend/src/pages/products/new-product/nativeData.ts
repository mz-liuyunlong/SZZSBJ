/** Source: owner's original V4 HTML, sample only; no API or production writes. */
export type Grade="S"|"A"|"B"|"C"|"D"|"Pass";
export type Product={id:string;sku:string;name:string;item:string;owner:string;days:number;market:number|null;marketReason:string;
scores:{speed:number;ad:number;profit:number;trust:number};penalties:number;penaltyFlags:string[];roi:number;margin:number;acos:number;
clicks:number;orders:number;qty7:number;sales30:number;spend:number;unitCost:number;price:number;inventory:number;risk:string;status:string;
suggested:number|null;requestQty:number|null;requestReason:string;tracking:string;sales60:number;sales90:number;margin60:number;acos60:number;
launch:string;arrival:string;sold30:number;sold60:number;sold90:number;actualQty:number;reasonFailure:string;
category?:string;developer?:string;operator?:string;overrides?:Partial<Record<"speed"|"ad"|"profit"|"trust",number>>};
export type Config={weights:{market:number;speed:number;ad:number;profit:number;trust:number};remindDays:number;successDays:30|60|90;successQty:number;successProfit:number;successAcos:number};
export const defaultConfig:Config={weights:{market:15,speed:30,ad:20,profit:25,trust:10},remindDays:30,successDays:60,successQty:200,successProfit:0,successAcos:35};
const original=[
{id:'NP-1001',sku:'YC00738',name:'双层隔热膜',item:'18420933001',owner:'王宁',days:16,market:10,marketReason:'同款链接少，核心竞对售价 $16.99，产品有差异化空间。',scores:{speed:10,ad:10,profit:3,trust:6},penalties:0,penaltyFlags:[],roi:.5,margin:15.3,acos:16.57,clicks:176,orders:18,qty7:13,sales30:42,spend:86,unitCost:9,price:13.99,inventory:124,risk:'ROI 较低',status:'待采购确认',suggested:null,requestQty:null,requestReason:'',tracking:'继续观察',sales60:76,sales90:105,margin60:16.8,acos60:28.4,launch:'2026-10-10',arrival:'2026-10-18',sold30:42,sold60:76,sold90:105,actualQty:350,reasonFailure:''},
{id:'NP-1002',sku:'YC00812',name:'厨房抽屉收纳盒',item:'18420933002',owner:'李敏',days:11,market:null,marketReason:'',scores:{speed:8,ad:8,profit:8,trust:8},penalties:0,penaltyFlags:[],roi:1.32,margin:22.5,acos:24.2,clicks:120,orders:12,qty7:10,sales30:25,spend:54,unitCost:7.5,price:19.99,inventory:86,risk:'待人工评分',status:'待市场评分',suggested:null,requestQty:null,requestReason:'',tracking:'等待开售',sales60:0,sales90:0,margin60:0,acos60:0,launch:'2026-10-15',arrival:'',sold30:0,sold60:0,sold90:0,actualQty:0,reasonFailure:''},
{id:'NP-1003',sku:'YC00921',name:'硅胶防滑垫套装',item:'18420933003',owner:'王宁',days:25,market:9,marketReason:'竞品较多但评价壁垒中等，套装有差异化。',scores:{speed:9,ad:8,profit:8,trust:7},penalties:0,penaltyFlags:[],roi:1.25,margin:21.4,acos:27.6,clicks:242,orders:26,qty7:18,sales30:66,spend:124,unitCost:8.4,price:14.99,inventory:213,risk:'采购申请待审',status:'审核中',suggested:null,requestQty:550,requestReason:'供应商整箱包装为 50 件一箱，且近期销量上升，申请增加备货。',tracking:'等待开售',sales60:0,sales90:0,margin60:0,acos60:0,launch:'2026-10-01',arrival:'',sold30:0,sold60:0,sold90:0,actualQty:0,reasonFailure:''},
{id:'NP-1004',sku:'YC01005',name:'可折叠桌面置物架',item:'18420933004',owner:'陈晨',days:61,market:8,marketReason:'竞争适中，价格有空间。',scores:{speed:8,ad:7,profit:8,trust:8},penalties:0,penaltyFlags:[],roi:1.4,margin:24.1,acos:26.3,clicks:312,orders:35,qty7:27,sales30:118,spend:168,unitCost:11,price:29.99,inventory:165,risk:'增长中',status:'已批准',suggested:null,requestQty:400,requestReason:'',tracking:'打品成功',sales60:245,sales90:350,margin60:24.8,acos60:25.1,launch:'2026-08-20',arrival:'2026-08-28',sold30:118,sold60:245,sold90:350,actualQty:400,reasonFailure:''},
{id:'NP-1005',sku:'YC01076',name:'真空收纳袋组合',item:'18420933005',owner:'李敏',days:18,market:7,marketReason:'市场竞争较强，套装组合仍有机会。',scores:{speed:6,ad:5,profit:7,trust:7},penalties:0,penaltyFlags:[],roi:.92,margin:17.2,acos:42.1,clicks:291,orders:8,qty7:4,sales30:18,spend:146,unitCost:8.2,price:21.99,inventory:53,risk:'高花费低转化',status:'待采购确认',suggested:null,requestQty:null,requestReason:'',tracking:'继续观察',sales60:0,sales90:0,margin60:0,acos60:0,launch:'2026-10-08',arrival:'',sold30:18,sold60:0,sold90:0,actualQty:0,reasonFailure:''},
{id:'NP-1006',sku:'YC01140',name:'硅胶水槽过滤网',item:'18420933006',owner:'陈晨',days:21,market:null,marketReason:'',scores:{speed:4,ad:4,profit:5,trust:5},penalties:2,penaltyFlags:['广告占比过高','低价依赖'],roi:.73,margin:13.1,acos:56.2,clicks:380,orders:5,qty7:1,sales30:7,spend:188,unitCost:3.1,price:8.99,inventory:410,risk:'广告花费偏高',status:'待市场评分',suggested:null,requestQty:null,requestReason:'',tracking:'等待开售',sales60:0,sales90:0,margin60:0,acos60:0,launch:'2026-10-05',arrival:'',sold30:7,sold60:0,sold90:0,actualQty:0,reasonFailure:''}
] as Product[];
const seventh={id:'NP-1007',sku:'YC01218',name:'折叠式水槽沥水架',item:'18420933007',owner:'王宁',days:36,market:null,marketReason:'',scores:{speed:7,ad:6,profit:8,trust:7},penalties:0,penaltyFlags:[],roi:1.08,margin:19.6,acos:31.4,clicks:205,orders:14,qty7:9,sales30:28,spend:73,unitCost:6.8,price:17.99,inventory:0,risk:'待人工评分',status:'待市场评分',suggested:null,requestQty:null,requestReason:'',tracking:'等待开售',sales60:0,sales90:0,margin60:0,acos60:0,launch:'2026-09-21',arrival:'',sold30:0,sold60:0,sold90:0,actualQty:0,reasonFailure:''} as Product;
const categoryMap={'NP-1001':'厨房用品','NP-1002':'收纳整理','NP-1003':'家居耗材','NP-1004':'办公收纳','NP-1005':'收纳整理','NP-1006':'厨房用品','NP-1007':'厨房用品'} as Record<string,string>;
const developerMap={'NP-1001':'王宁','NP-1002':'李敏','NP-1003':'王宁','NP-1004':'陈晨','NP-1005':'李敏','NP-1006':'陈晨','NP-1007':'王宁'} as Record<string,string>;
export const samples:Product[]=[...original,seventh].map(p=>({...p,category:categoryMap[p.id],developer:developerMap[p.id],operator:p.owner}));
export const categoryStats=[
{name:'收纳用品',tested:28,passed:14,rate:50,avg:7.6,success:42.9,deep:'持续观察',tone:'blue'},
{name:'厨房用品',tested:24,passed:12,rate:50,avg:7.4,success:33.3,deep:'拆分细分类目',tone:'orange'},
{name:'家居耗材',tested:18,passed:10,rate:55.6,avg:7.9,success:60,deep:'重点拓展',tone:'green'},
{name:'办公打包',tested:20,passed:6,rate:30,avg:6.7,success:16.7,deep:'深挖失败原因',tone:'red'},
{name:'家居小件',tested:14,passed:5,rate:35.7,avg:6.8,success:20,deep:'样本继续积累',tone:'gray'}
];
export const developerStats=[{name:'王宁',tested:26,passed:14,rate:53.8,avg:7.8},{name:'林晓',tested:24,passed:13,rate:54.2,avg:7.6},{name:'陈佳',tested:21,passed:9,rate:42.9,avg:7.2},{name:'赵敏',tested:19,passed:7,rate:36.8,avg:6.9}];
export const operatorStats=[{name:'陈佳',tracked:18,success:7,rate:38.9,avgProfit:2380},{name:'王宁',tracked:16,success:6,rate:37.5,avgProfit:1940},{name:'李倩',tracked:14,success:5,rate:35.7,avgProfit:1620},{name:'赵敏',tracked:12,success:3,rate:25,avgProfit:980}];
export const bands:Record<Grade,[number,number]>={S:[400,600],A:[300,500],B:[200,400],C:[150,250],D:[0,0],Pass:[0,0]};
export function score(p:Product,c:Config){if(p.market===null)return null;const w=c.weights,o=p.overrides||{};
return Math.round(((p.market*w.market+(o.speed??p.scores.speed)*w.speed+(o.ad??p.scores.ad)*w.ad+
(o.profit??p.scores.profit)*w.profit+(o.trust??p.scores.trust)*w.trust)/100-p.penalties)*100)/100}
export function grade(p:Product,c:Config):Grade|null{const s=score(p,c);if(s===null)return null;if(p.roi<.5)return"Pass";
let g:Grade=s>=9?"S":s>=8?"A":s>=7?"B":s>=6?"C":"D";
if(p.roi<.8&&(g==="S"||g==="A"))g="B";return g}
export function suggestion(p:Product,c:Config){const g=grade(p,c);if(g===null||g==="Pass"||g==="D")return 0;
const [lo,hi]=bands[g];return Math.max(lo,Math.min(hi,Math.round((p.qty7/7*30)/10)*10))}
export const percent=(n:number,d:number)=>d?(100*n/d).toFixed(1)+"%":"—";
