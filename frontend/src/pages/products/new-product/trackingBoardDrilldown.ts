/** PR337_TRACKING_DRILL_V5: view-only filter contract shared by dashboard and detail page. */
import { grade, type Config, type Product } from './nativeData';
import { observationBucket, type TrackingProduct } from './trackingBoardMetrics';
export { isOverdueHumanReview } from './trackingBoardMetrics';

export type TrackingDrillKind='all'|'owner'|'grade'|'category'|'secondary'|'observation'|'item';
export type TrackingDrillFilter={
  kind:TrackingDrillKind;
  label:string;
  from:string;
  to:string;
  value?:string;
  parentCategory?:string;
};
export const trackingOwner=(row:Product)=>row.operator?.trim()||row.owner?.trim()||'未分配';
export const trackingGrade=(row:Product,cfg:Config)=>
  (row as TrackingProduct).initialGrade??grade(row,cfg)??'待评分';
export const trackingSecondary=(row:Product)=>{
  const ext=row as TrackingProduct;
  return ext.secondaryCategory||ext.subcategory||ext.category2||'未分类';
};
const isISO=(v:string)=>/^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v+'T00:00:00Z'));
export function matchesTrackingBoardDrill(row:Product,filter:TrackingDrillFilter|null):boolean{
  if(!filter)return true;
  const date=row.arrival||row.launch;
  if(!isISO(date)||!isISO(filter.from)||!isISO(filter.to)||date<filter.from||date>filter.to)return false;
  switch(filter.kind){
    case 'category':return (row.category?.trim()||'未分类')===filter.value;
    case 'secondary':return trackingSecondary(row)===filter.value &&
      (!filter.parentCategory||(row.category?.trim()||'未分类')===filter.parentCategory);
    case 'observation':return observationBucket(row,filter.to)===filter.value;
    case 'owner':case 'grade':case 'item':case 'all':return true;
  }
}
