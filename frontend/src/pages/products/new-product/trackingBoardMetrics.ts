/** Tracking dashboard read-only view model. Uses PR337's current Product records; no fabricated statistics. */
import { grade, type Config, type Grade, type Product } from './nativeData';

export type TrackingOutcome = '打品成功' | '打品失败' | '继续观察' | '需要优化' | '等待开售' | '未确认';
export type TrackingCategoryRow = {
  key:string; category:string; total:number; success:number; failed:number; pending:number;
  rate:number|null; recommendation:'样本不足'|'待配置'; products:Product[];
};
export type TrackingOwnerRow={key:string; name:string; total:number; success:number; failed:number; rate:number|null; products:Product[]};
export type TrackingGradeRow={key:string; grade:Grade|'待评分'; total:number; products:Product[]};
export type TrackingObservationRow={key:string; label:string; total:number; success:number; failed:number; stable:number; pending:number; unknown:number; rate:number|null; products:Product[]};
export type TrackingView={
  all:Product[]; pool:Product[]; due:Product[]; success:Product[]; failed:Product[]; successRate:number|null;
  successCategories:number; pendingCategories:number; grades:TrackingGradeRow[]; owners:TrackingOwnerRow[];
  categories:TrackingCategoryRow[]; observations:TrackingObservationRow[];
  secondary:TrackingCategoryRow[]; noSecondary:number;
};
export type TrackingProduct=Product & { initialGrade?:Grade; secondaryCategory?:string|null; subcategory?:string|null; category2?:string|null };
const grades:readonly (Grade|'待评分')[]=['S','A','B','C','D','Pass','待评分'];
const outcome=(p:Product):TrackingOutcome => {
  if(p.tracking==='打品成功')return '打品成功';
  if(p.tracking==='打品失败')return '打品失败';
  if(p.tracking==='继续观察')return '继续观察';
  if(p.tracking==='需要优化')return '需要优化';
  if(p.tracking==='等待开售')return '等待开售';
  return '未确认';
};
const rate=(a:number,b:number):number|null=>b===0?null:100*a/b;
const dateMs=(value:string):number|null=>{
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
  const [year,month,day]=value.split('-').map(Number);
  const ms=Date.UTC(year,month-1,day);
  return new Date(ms).toISOString().slice(0,10)===value?ms:null;
};
export const daysBetween=(start:string,end:string):number|null=>{
  const a=dateMs(start),b=dateMs(end);
  return a===null||b===null?null:Math.floor((b-a)/86400000);
};
const inWindow=(date:string,from:string,to:string):boolean => {
  const value=dateMs(date),a=dateMs(from),b=dateMs(to);
  return value!==null&&a!==null&&b!==null&&value>=a&&value<=b;
};
/** True only if >45 full natural days have elapsed and no terminal human verdict exists.
 * Local Mock uses arrival as the sellable-start proxy; production requires a real sellable date. */
export function isOverdueHumanReview(p:Product,asOf:string,threshold=45):boolean{
  const age=daysBetween(p.arrival,asOf);
  return age!==null&&age>threshold&&p.tracking!=='打品成功'&&p.tracking!=='打品失败';
}
export function getTrackingPool(products:Product[]):Product[]{
  return products.filter(p=>p.actualQty>0 || p.status==='已批准' || outcome(p)==='打品成功' || outcome(p)==='打品失败');
}
function groupCategory(products:Product[],pick:(p:TrackingProduct)=>string):TrackingCategoryRow[]{
  const groups=new Map<string,Product[]>();
  for(const p of products){const name=pick(p as TrackingProduct);if(!groups.has(name))groups.set(name,[]);groups.get(name)!.push(p);}
  return [...groups].map(([category,ps])=>{
    const success=ps.filter(p=>outcome(p)==='打品成功').length;
    const failed=ps.filter(p=>outcome(p)==='打品失败').length;
    return {key:category,category,total:ps.length,success,failed,pending:ps.length-success-failed,
      rate:rate(success,success+failed),recommendation:(success+failed<5?'样本不足':'待配置') as TrackingCategoryRow['recommendation'],products:ps};
  }).sort((a,b)=>b.total-a.total||a.category.localeCompare(b.category));
}
function getSecondary(p:TrackingProduct):string|null{return p.secondaryCategory||p.subcategory||p.category2||null}
function groupSecondary(products:Product[]):TrackingCategoryRow[]{
  const groups=new Map<string,Product[]>();
  for(const p of products){
    const parent=p.category?.trim()||'未分类';
    const second=getSecondary(p as TrackingProduct)??'未分类';
    const key=JSON.stringify([parent,second]);
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key)!.push(p);
  }
  return [...groups].map(([key,rows])=>{
    const ok=rows.filter(p=>outcome(p)==='打品成功').length;
    const failed=rows.filter(p=>outcome(p)==='打品失败').length;
    return {key,category:getSecondary(rows[0] as TrackingProduct)??'未分类',total:rows.length,
      success:ok,failed,pending:rows.length-ok-failed,rate:rate(ok,ok+failed),
      recommendation:(ok+failed<5?'样本不足':'待配置') as TrackingCategoryRow['recommendation'],products:rows};
  }).sort((a,b)=>b.total-a.total||a.key.localeCompare(b.key));
}
const bucketNames=['0–29天','30–59天','60–89天','90–119天','120–149天','150–179天','180天及以上','无到货时间'];
export function observationBucket(p:Product,end:string):string{
  const elapsed=daysBetween(p.arrival,end);
  if(elapsed===null||elapsed<0)return '无到货时间';
  if(elapsed<30)return bucketNames[0];if(elapsed<60)return bucketNames[1];if(elapsed<90)return bucketNames[2];
  if(elapsed<120)return bucketNames[3];if(elapsed<150)return bucketNames[4];
  if(elapsed<180)return bucketNames[5];return bucketNames[6];
}
export function buildTrackingView(products:Product[],cfg:Config,from:string,to:string):TrackingView{
  // The entry date is arrival if available, otherwise launch. Historical status snapshots do not exist in PR337 Mock.
  const all=products.filter(p=>inWindow(p.arrival||p.launch,from,to));
  const pool=getTrackingPool(all);
  const success=pool.filter(p=>outcome(p)==='打品成功');
  const failed=pool.filter(p=>outcome(p)==='打品失败');
  // PR337: manual tracking decision overdue strictly AFTER 45 days from arrival/sellable proxy.
  const due=pool.filter(p=>isOverdueHumanReview(p,to));
  const categories=groupCategory(pool,p=>p.category?.trim()||'未分类');
  const secondaryAvailable=pool.filter(p=>getSecondary(p as TrackingProduct));
  const secondary=groupSecondary(secondaryAvailable);
  const ownerMap=new Map<string,Product[]>();
  for(const p of pool){const owner=p.operator?.trim()||p.owner||'未分配';if(!ownerMap.has(owner))ownerMap.set(owner,[]);ownerMap.get(owner)!.push(p);}
  const owners=[...ownerMap].map(([name,ps])=>{
    const ok=ps.filter(p=>outcome(p)==='打品成功').length;
    const no=ps.filter(p=>outcome(p)==='打品失败').length;
    return {key:name,name,total:ps.length,success:ok,failed:no,rate:rate(ok,ok+no),products:ps};
  }).sort((a,b)=>b.total-a.total||a.name.localeCompare(b.name));
  const gradeRows:TrackingGradeRow[]=grades.map(key=>({key,grade:key,
    products:pool.filter(p=>((p as TrackingProduct).initialGrade??grade(p,cfg)??'待评分')===key),total:0}));
  for(const g of gradeRows)g.total=g.products.length;
  const observations:TrackingObservationRow[]=bucketNames.map(label=>{
    const ps=pool.filter(p=>observationBucket(p,to)===label);
    const ok=ps.filter(p=>outcome(p)==='打品成功').length;
    const no=ps.filter(p=>outcome(p)==='打品失败').length;
    const stable=ps.filter(p=>outcome(p)==='继续观察').length;
    const pending=ps.filter(p=>outcome(p)==='需要优化'||outcome(p)==='等待开售').length;
    return {key:label,label,total:ps.length,success:ok,failed:no,stable,pending,unknown:ps.length-ok-no-stable-pending,
      rate:rate(ok,ok+no),products:ps};
  });
  return {all,pool,due,success,failed,successRate:rate(success.length,pool.length),
    successCategories:new Set(success.map(p=>p.category||'未分类')).size,
    pendingCategories:new Set(due.map(p=>p.category||'未分类')).size,
    grades:gradeRows,owners,categories,observations,secondary,noSecondary:pool.length-secondaryAvailable.length};
}
export const rateText=(value:number|null)=>value===null?'—':`${value.toFixed(1)}%`;
export const observationNames=bucketNames;
