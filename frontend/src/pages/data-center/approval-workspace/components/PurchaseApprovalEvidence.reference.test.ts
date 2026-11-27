import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import PurchaseApprovalEvidence, { approvalScoreDisplay } from './PurchaseApprovalEvidence';
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


// NP_PURCHASE_SCORE_GRADE_EVIDENCE_V1
// NP_PURCHASE_SCORE_HOVER_HEADER_V2
it('uses frozen totals and grade in the top metric only',()=>{
  const data={...evidence(),system_grade:'D' as const,effective_grade:'C' as const,system_total:'5.40',effective_total:'6.80'};
  expect(approvalScoreDisplay(data)).toMatchObject({previous:'5.40',gradeChange:'D级 → C级',revised:true});
  expect(render(data)).not.toContain('等级变化');
});
it('does not invent an unknown baseline',()=>{
  const data={...evidence(),system_grade:null,effective_grade:'C' as const,system_total:null,effective_total:'6.80'};
  expect(approvalScoreDisplay(data)).toMatchObject({previous:null,gradeChange:null,revised:true});
});
// NP_PURCHASE_REASON_TOOLTIP_V3
it('shows correction reason without a separate history entry or dialog',()=>{
  const html=render(evidence());
  expect(html).toContain('sample revised reason');
  expect(html).toContain('purchase-evidence__correction-preview');
  expect(html).not.toContain('查看修正记录');
  expect(html).not.toContain('purchase-evidence__history-toggle');
  expect(html).not.toContain('评分修正记录 ·');
});
it('retains the last reason when the original score has been restored',()=>{
  const data=evidence();
  data.effective_dimensions={...data.system_dimensions};
  const html=render(data);
  expect(html).toContain('已恢复系统原始评分');
  expect(html).toContain('sample revised reason');
  expect(html).not.toContain('查看修正记录');
});
