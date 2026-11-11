import { describe, expect, it } from 'vitest';
import { samples, defaultConfig } from './nativeData';
import { buildTrackingView } from './trackingBoardMetrics';
import { isOriginalPr337Mock, isTrackingVisualSample, withTrackingVisualSamples } from './trackingBoardVisualSamples';

const anchor='2026-11-11';
describe('PR337 tracking board uses one typed Product[] data path',()=>{
  it('only adds presentation records to the seven original PR337 local Mock products',()=>{
    expect(isOriginalPr337Mock(samples)).toBe(true);
    const rows=withTrackingVisualSamples(samples,anchor);
    expect(rows).toHaveLength(55);
    expect(rows.slice(0,7)).toEqual(samples);
    expect(rows.slice(7).every(isTrackingVisualSample)).toBe(true);
    expect(new Set(rows.map(x=>x.id)).size).toBe(rows.length);
    expect(rows.slice(7).every(x=>/^YC\d{5}$/.test(x.sku) && /^\d{11}$/.test(x.item))).toBe(true);
    expect(rows.slice(7).some(x=>x.tracking==='打品成功')).toBe(true);
    expect(rows.slice(7).some(x=>x.tracking==='打品失败')).toBe(true);
  });
  it('never pads partial/real API inputs and never mutates product arrays',()=>{
    const actual=[{...samples[0],id:'real-api-item-1'}];
    expect(withTrackingVisualSamples(actual,anchor)).toBe(actual);
    expect(withTrackingVisualSamples([],anchor)).toHaveLength(0);
    expect(withTrackingVisualSamples(samples.slice(0,3),anchor)).toHaveLength(3);
    expect(samples).toHaveLength(7);
  });
  it('has enough rows in the normal date range to test table scrolling, all filters and categories',()=>{
    const rows=withTrackingVisualSamples(samples,anchor);
    const view=buildTrackingView(rows,defaultConfig,'2026-09-13',anchor);
    expect(view.all.length).toBeGreaterThan(25);
    expect(view.owners.length).toBeGreaterThan(4);
    expect(view.categories.length).toBeGreaterThan(8);
    expect(view.secondary.length).toBeGreaterThan(10);
    expect(view.grades.reduce((n,g)=>n+g.total,0)).toBe(view.pool.length);
    expect(view.success.length).toBeGreaterThan(0);
    expect(view.failed.length).toBeGreaterThan(0);
  });
  it('respects date range instead of hardcoding stats',()=>{
    const rows=withTrackingVisualSamples(samples,anchor);
    const all=buildTrackingView(rows,defaultConfig,'2026-09-13',anchor);
    const short=buildTrackingView(rows,defaultConfig,'2026-11-05',anchor);
    expect(short.all.length).toBeLessThan(all.all.length);
  });
});
