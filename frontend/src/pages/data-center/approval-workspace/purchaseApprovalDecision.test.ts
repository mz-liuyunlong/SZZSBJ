import {describe, expect, it} from 'vitest';
import {buildDemoDailySales90} from './purchaseApprovalDemoMetrics';
import {demoProfiles} from './approvalDemoPresentation';
import drawerSource from './components/PurchaseApprovalDecisionDrawer.tsx?raw';

describe('purchase approval decision detail V3', () => {
  it('keeps demo daily sales consistent with the same purchase profile', () => {
    for (const id of ['DEMO-PO-002', 'DEMO-PO-003']) {
      const profile = demoProfiles[id];
      const series = profile.purchaseAnalysis?.dailySales90;
      expect(series).toHaveLength(90);
      expect(series?.slice(-30).reduce((sum,n) => sum+n, 0)).toBe(profile.sales30Qty);
      expect(series?.every(n => n >= 0 && Number.isFinite(n))).toBe(true);
    }
  });
  it('does not invent a series when there is no valid aggregate', () => {
    expect(buildDemoDailySales90(-1, 1)).toEqual([]);
    expect(buildDemoDailySales90(Number.NaN, 1)).toEqual([]);
  });
  it('has a weighted score snapshot consistent with the first-purchase total', () => {
    const p=demoProfiles['DEMO-PO-001'];
    const s=p.purchaseAnalysis?.dimensions;
    expect(s).toBeDefined();
    if (!s) return;
    const total=s.market*.15+s.speed*.3+s.ad*.2+s.profit*.25+s.trust*.1;
    expect(Number(total.toFixed(2))).toBe(p.scoreTotal);
  });
  it('keeps first-purchase and replenishment analysis independent', () => {
    expect(drawerSource).toContain('FiveDimensions');
    expect(drawerSource).toContain('ReplenishmentAnalysis');
    expect(drawerSource).toContain('DailySalesChart');
    expect(drawerSource).toContain("onAction?.(record, 'approve')");
    expect(drawerSource).toContain("onAction?.(record, 'reject')");
  });
});
