import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import PurchaseApprovalEvidence from './PurchaseApprovalEvidence';
import type { ApprovalItem, PurchaseApprovalEvidenceView } from '../approvalTypes';

function evidence(): PurchaseApprovalEvidenceView {
  const dimensions = {speed:'4.60',ad:'2.00',profit:'0.00',trust:'4.60',market:'7.00'};
  return {
    frozen: true,
    score_rule_version: 8,
    system_dimensions: dimensions,
    effective_dimensions: {...dimensions,speed:'6.00',profit:'3.00'},
    weights: {speed:30,ad:20,profit:25,trust:10,market:15},
    correction_history: [
      {dimension:'speed',before:'4.60',after:'6.00',reason:'sample revised reason',actor_id:'operator',at:null,revision:1},
      {dimension:'profit',before:'0.00',after:'3.00',reason:'another reason',actor_id:'operator',at:null,revision:2},
    ],
    manual_risks: ['\u65e0'],
    system_risks: [],
    competitor_ids: [],
    no_competitors: true,
    market_reason: 'reviewed competitive positioning',
    manual_conclusion: null,
  };
}
function row(data:PurchaseApprovalEvidenceView,requested=100,suggested=200): ApprovalItem {
  return {approval_type:'new_product_purchase',purchase_details:{approval_evidence:data,requested_qty:requested,suggested_qty:suggested,initial_grade:'C'},reason:'request reason'} as ApprovalItem;
}
const render = (data:PurchaseApprovalEvidenceView,requested?:number,suggested?:number) => renderToStaticMarkup(
  createElement(PurchaseApprovalEvidence,{record:row(data,requested,suggested)})
);

describe('reference approval evidence V2',()=>{
  it('retains five equal dimensions with source-backed corrections',()=>{
    const html=render(evidence());
    expect((html.match(/class="purchase-evidence__score-card /g)??[])).toHaveLength(5);
    expect(html).toContain('4.60');
    expect(html).toContain('6.00');
    expect(html).toContain('3.00');
    expect(html).toContain('purchase-evidence__correction-preview');
  });
  it('explicit risk none is green, while competitor none is red',()=>{
    const html=render(evidence());
    expect(html).toMatch(/purchase-evidence__pill--green[^>]*>\u65e0/);
    expect(html).toMatch(/purchase-evidence__pill--red[^>]*>\u65e0/);
  });
  it('hides quantity reason when application equals suggestion',()=>{
    expect(render(evidence(),200,200)).not.toContain('purchase-evidence__qty');
    expect(render(evidence(),100,200)).toContain('purchase-evidence__qty');
  });
  it('does not make unknown competitor selection a red none',()=>{
    const current = {...evidence(),no_competitors:null,competitor_ids:null};
    const html = render(current);
    expect(html).toMatch(/purchase-evidence__pill--muted/);
    expect(html).not.toMatch(/purchase-evidence__pill--red[^>]*>\u65e0/);
  });
});
