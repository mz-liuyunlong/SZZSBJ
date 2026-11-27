import { expect, it } from 'vitest';
import { evidenceDimensionStatus, shouldShowPurchaseReason } from './PurchaseApprovalEvidence';
import type { PurchaseApprovalEvidenceView } from '../approvalTypes';

const source: PurchaseApprovalEvidenceView = {
  frozen: true, score_rule_version: 12,
  system_dimensions: {market:'7',speed:'4.6',ad:'2',profit:'0',trust:'4.6'},
  effective_dimensions: {market:'7',speed:'6',ad:'2',profit:'3',trust:'4.6'},
  weights: {market:15,speed:30,ad:20,profit:25,trust:10},
  correction_history: [], manual_risks:['无'], system_risks:[],
  competitor_ids:[], no_competitors:true,market_reason:null,manual_conclusion:null,
};

it('uses frozen original and corrected numbers, rather than latest scores',()=>{
  expect(evidenceDimensionStatus(source,'speed').status).toBe('changed');
  expect(evidenceDimensionStatus(source,'profit').original).toBe(0);
  expect(evidenceDimensionStatus(source,'ad').status).toBe('unchanged');
  expect(evidenceDimensionStatus(source,'market').status).toBe('manual');
});
it('shows the request explanation only for a real quantity deviation',()=>{
  expect(shouldShowPurchaseReason(100,200)).toBe(true);
  expect(shouldShowPurchaseReason(200,200)).toBe(false);
  expect(shouldShowPurchaseReason(null,200)).toBe(false);
});
