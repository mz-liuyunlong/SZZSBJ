import { describe, expect, it } from 'vitest';
import { calculateConfirmedScore, confirmedScoringDefaults as p, confirmedOverallWeights as w, createScoreSnapshot,
  demoFactsFromProduct, higherBetter, lowerBetter, validateScoringParameters, type ScoringFacts } from './NewProductConfirmedScoring';
const sample:ScoringFacts={firstOrderDay:2,elapsedDays:14,ordersInWindow:14,adStatus:'active',
  adClicks:50,adSpend:29,adOrders:4,adRevenue:100,
  roi:1,grossMarginPct:17.5,validSoldUnits:20,validOrders:14,singleUnitOrders:12,marketScore:7};
describe('PR337 confirmed scoring business contract',()=>{
  it('validates all confirmed default numeric parameters',()=>expect(validateScoringParameters(p)).toBeNull());
  it('scores first order 3 days full, 7 days 6.3636, 14 days zero',()=>{
    const s={...sample,adStatus:'not_run' as const};
    expect(calculateConfirmedScore({...s,firstOrderDay:3},p,w).dimensions.speed.details[0].score).toBe(10);
    expect(calculateConfirmedScore({...s,firstOrderDay:7},p,w).dimensions.speed.details[0].score).toBeCloseTo(70/11,8);
    expect(calculateConfirmedScore({...s,firstOrderDay:14},p,w).dimensions.speed.details[0].score).toBe(0);
  });
  it('counts distinct orders not units, with 14-day 20-order target',()=>{
    const d=calculateConfirmedScore({...sample,ordersInWindow:10},p,w).dimensions.speed;
    expect(d.details[1].score).toBe(5);
    expect(d.score).toBe(7);
  });
  it('ACOS 29% 8.20; CPC $1.00 8.333; CVR 5% 5.00; combined 6.9467',()=>{
    expect(lowerBetter(29,20,70)).toBeCloseTo(8.2);
    expect(lowerBetter(1,.8,2)).toBeCloseTo(8.333333);
    expect(higherBetter(5,2,8)).toBeCloseTo(5);
    const d=calculateConfirmedScore({...sample,adClicks:20,adSpend:20,adOrders:1,adRevenue:20/0.29},p,w).dimensions.ad;
    // actual ACOS is 29%, CPC 1, CVR 5%
    expect(d.score).toBeCloseTo(6.9466666667,8);
  });
  it('includes live ad score even under 20 clicks',()=>{
    const d=calculateConfirmedScore({...sample,adClicks:10,adOrders:1},p,w);
    expect(d.adSampleInsufficient).toBe(true);
    expect(d.dimensions.ad.score).not.toBeNull();
  });
  it('paid clicks with no attribution score 0 ACOS/CVR and normal CPC',()=>{
    const d=calculateConfirmedScore({...sample,adClicks:15,adSpend:12,adOrders:0,adRevenue:0},p,w).dimensions.ad;
    expect(d.details[0].score).toBe(0);
    expect(d.details[1].score).toBe(10);
    expect(d.details[2].score).toBe(0);
    expect(d.score).toBe(2);
  });
  it('unknown ad availability is not assumed to mean no ads',()=>{
    const d=calculateConfirmedScore({...sample,adStatus:'unknown'},p,w);
    expect(d.adExcluded).toBe(false);
    expect(d.total).toBeNull();
  });
  it('verified no ads with natural orders excludes 20% ad weight',()=>{
    const d=calculateConfirmedScore({...sample,adStatus:'not_run'},p,w);
    expect(d.adExcluded).toBe(true);
    expect(d.total).not.toBeNull();
    const base=(7*15+d.dimensions.speed.score!*30+d.dimensions.profit.score!*25+d.dimensions.trust.score!*10)/80;
    expect(d.total).toBeCloseTo(base,8);
  });
  it('14 days with no ads or orders remains continue-observation not Pass',()=>{
    const d=calculateConfirmedScore({...sample,adStatus:'not_run',firstOrderDay:null,ordersInWindow:0,
      validOrders:0,validSoldUnits:0,singleUnitOrders:0,roi:null,grossMarginPct:null},p,w);
    expect(d.status).toBe('continue_observation');
    expect(d.grade).toBeNull();
  });
  it('profit 1.0 ROI and 17.5% margin score 5',()=>expect(calculateConfirmedScore(sample,p,w).dimensions.profit.score).toBe(5));
  it('trust 10 units, 65% single-unit orders yields 5',()=>{
    const d=calculateConfirmedScore({...sample,validSoldUnits:10,validOrders:20,singleUnitOrders:13},p,w);
    expect(d.dimensions.trust.score).toBe(5);
  });
  it('missing first order, ad attribution or order composition blocks final grade',()=>{
    const demo=demoFactsFromProduct({market:7,roi:1,margin:17.5,acos:25,clicks:20,spend:10});
    const d=calculateConfirmedScore(demo,p,w);
    expect(d.grade).toBeNull();
    expect(d.dimensions.profit.score).toBe(5);
  });
  it('risk score limits use exact thresholds; human rules require explicit confirmation',()=>{
    const ris={vetoes:[{name:'ROI 低（Pass）',enabled:true,action:'Pass'},
      {name:'ROI 低（评级上限）',enabled:true,action:'最多 B 级'},
      {name:'合规风险',enabled:true,action:'Pass'}]};
    const rich={...sample,marketScore:10,firstOrderDay:1,ordersInWindow:20,adStatus:'not_run' as const,
      grossMarginPct:25,validSoldUnits:20,validOrders:20,singleUnitOrders:20};
    expect(calculateConfirmedScore({...rich,roi:.49},p,w,ris).grade).toBe('Pass');
    expect(calculateConfirmedScore({...rich,roi:.79},p,w,ris).grade).toBe('B');
    expect(calculateConfirmedScore({...rich,roi:1.5},p,w,ris).grade).toBe('S');
    expect(calculateConfirmedScore({...rich,roi:1.5},p,w,{...ris,confirmedRiskNames:['合规风险']}).grade).toBe('Pass');
  });
  it('freezes snapshots without mutating prior data',()=>{
    const result=calculateConfirmedScore(sample,p,w);
    const snapshot=createScoreSnapshot('v1',sample,result);
    sample.marketScore=4;
    expect(snapshot.sourceFacts.marketScore).toBe(7);
    expect(snapshot.version).toBe('v1');
  });
  it('does not round before grading: 8.999 displays 9.00 but remains A',()=>{
    // Grade helper used by calculation must inspect raw total; test with unmodified weighted market-only?
    const almost={...sample,marketScore:8.999,firstOrderDay:1,ordersInWindow:20,
      adStatus:'not_run' as const,roi:1.5,grossMarginPct:25,validSoldUnits:20,
      validOrders:20,singleUnitOrders:20};
    const d=calculateConfirmedScore(almost,p,{market:100,speed:0,ad:0,profit:0,trust:0});
    expect(d.grade).toBe('A');
    expect(d.total?.toFixed(2)).toBe('9.00');
  });
});
