import {describe,it,expect} from 'vitest';
import { defaultConfig, samples, type Product } from './nativeData';
import {isOverdueHumanReview,matchesTrackingBoardDrill,trackingOwner} from './trackingBoardDrilldown';
const row:Product={...samples[3],arrival:'2026-09-20',tracking:'继续观察',category:'厨房用品',operator:'王宁'};
describe('PR337 tracking board drill and 45-day human-review reminder',()=>{
 it('45 days exactly not overdue; day 46 is',()=>{
  expect(isOverdueHumanReview(row,'2026-11-04')).toBe(false);
  expect(isOverdueHumanReview(row,'2026-11-05')).toBe(true);
 });
 it('terminal success or failure never appears in overdue reminder',()=>{
  expect(isOverdueHumanReview({...row,tracking:'打品成功'},'2026-11-11')).toBe(false);
  expect(isOverdueHumanReview({...row,tracking:'打品失败'},'2026-11-11')).toBe(false);
  expect(isOverdueHumanReview({...row,tracking:'需要优化'},'2026-11-11')).toBe(true);
 });
 it('missing arrival date is not inferred from listed days',()=>{
  expect(isOverdueHumanReview({...row,arrival:''},'2026-11-11')).toBe(false);
 });
 it('checks dashboard date range and category',()=>{
  expect(matchesTrackingBoardDrill(row,{kind:'category',label:'厨房用品',value:'厨房用品',from:'2026-09-01',to:'2026-11-11'})).toBe(true);
  expect(matchesTrackingBoardDrill(row,{kind:'category',label:'厨房用品',value:'厨房用品',from:'2026-10-01',to:'2026-11-11'})).toBe(false);
 });
 it('owner uses operator responsibility consistently',()=>{
  expect(trackingOwner(row)).toBe('王宁');
  expect(defaultConfig.weights.speed).toBe(30);
 });
});
