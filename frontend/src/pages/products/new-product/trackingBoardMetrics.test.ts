import { describe, expect, it } from 'vitest';
import { defaultConfig, type Product } from './nativeData';
import { buildTrackingView, daysBetween, getTrackingPool } from './trackingBoardMetrics';
const row=(id:string,overrides:Partial<Product>={}):Product=>({
  id,sku:`SKU-${id}`,item:`IT-${id}`,name:`商品${id}`,owner:'王宁',days:35,
  market:7,marketReason:'',scores:{speed:7,ad:7,profit:7,trust:7},penalties:0,penaltyFlags:[],
  roi:1,margin:20,acos:20,clicks:10,orders:5,qty7:3,sales30:15,spend:5,unitCost:3,price:8,inventory:20,risk:'',
  status:'已批准',suggested:100,requestQty:100,requestReason:'',tracking:'继续观察',sales60:20,sales90:30,
  margin60:20,acos60:20,launch:'2026-10-01',arrival:'2026-10-10',sold30:15,sold60:20,sold90:30,
  actualQty:20,reasonFailure:'',category:'厨房用品',developer:'王宁',operator:'王宁',...overrides
});
describe('tracking dashboard summary from actual source records',()=>{
  it('computes pool, achieved and failed outcomes without hardcoded screenshot numbers',()=>{
    const rows=[row('a',{tracking:'打品成功'}),row('b',{tracking:'打品失败'}),row('c',{tracking:'继续观察'})];
    const out=buildTrackingView(rows,defaultConfig,'2026-09-01','2026-11-11');
    expect(out.pool).toHaveLength(3);expect(out.success).toHaveLength(1);expect(out.failed).toHaveLength(1);
    expect(out.successRate).toBeCloseTo(100/3);
    expect(out.owners[0].rate).toBe(50); // operator table uses completed success vs failure
    expect(out.categories[0].pending).toBe(1);expect(out.categories[0].rate).toBe(50);
  });
  it('filters the date range by known entry date, without pretending to have historic snapshots',()=>{
    const rows=[row('a',{arrival:'2026-08-20'}),row('b',{arrival:'2026-10-20'})];
    const out=buildTrackingView(rows,defaultConfig,'2026-09-01','2026-11-11');
    expect(out.all.map(p=>p.id)).toEqual(['b']);
  });
  it('computes days since arrival from calendar dates not p.days',()=>{
    expect(daysBetween('2026-10-10','2026-11-11')).toBe(32);
    const out=buildTrackingView([row('a',{arrival:'2026-10-10',days:2})],defaultConfig,'2026-09-01','2026-11-11');
    expect(out.observations.find(x=>x.label==='30–59天')?.total).toBe(1);
  });
  it('never fabricates secondary categories',()=>{
    const view=buildTrackingView([row('a')],defaultConfig,'2026-09-01','2026-11-11');
    expect(view.secondary).toHaveLength(0);expect(view.noSecondary).toBe(1);
  });
  it('shows human decision reminders only after 45 full days',()=>{
    const asOf='2026-11-11';
    const view=buildTrackingView([
      row('a',{market:null,days:2,arrival:'2026-09-26',tracking:'继续观察'}),
      row('b',{market:null,days:100,arrival:'2026-09-27',tracking:'继续观察'}),
      row('c',{market:7,days:100,arrival:'2026-09-26',tracking:'打品成功'}),
      row('d',{market:7,days:100,arrival:'2026-09-26',tracking:'打品失败'}),
    ],defaultConfig,'2026-09-01',asOf);
    expect(daysBetween('2026-09-27',asOf)).toBe(45);
    expect(daysBetween('2026-09-26',asOf)).toBe(46);
    expect(view.due.map(p=>p.id)).toEqual(['a']);
    expect(view.pendingCategories).toBe(1);
  });
  it('does not treat unapproved, unpurchased products as tracking pool',()=>{
    const product=row('a',{actualQty:0,status:'待市场评分',tracking:'等待开售'});
    expect(getTrackingPool([product])).toHaveLength(0);
  });
});
