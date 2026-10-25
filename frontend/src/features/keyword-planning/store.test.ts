import {beforeEach,expect,it} from 'vitest';
import type {KeywordResult,KeywordRun} from '@/api/keywordPlanningV11Api';
import {useKeywordStore} from './store';

const run:KeywordRun={
  run_id:'00000000-0000-0000-0000-000000000001',
  product_id:'00000000-0000-0000-0000-000000000002',
  source_account_ref:'synthetic-account',item_id:'123456789',status:'blocked',
  rule_version_id:'00000000-0000-0000-0000-000000000003',
  created_at:'2026-01-15T00:00:00Z',finished_at:null,keyword_count:1,
};
const result:KeywordResult={
  term_id:'00000000-0000-0000-0000-000000000004',keyword:'synthetic organizer',
  primary_type:'人工确认词',page_coverage:'页面看不出来',core_root:null,
  score:null,match_points:null,intent_points:null,page_points:4,root_points:null,
  data_points:null,risk_points:0,base_grade:null,allocation_grade:null,
  exact_selected:false,broad_selected:false,broad_role:null,
  suggested_optimization_bid:null,decision_status:'review',risk_reasons:['SCORE_EVIDENCE_REQUIRED'],
  exact_reason:'SCORE_EVIDENCE_REQUIRED',broad_reason:null,quality_note:null,
  rank_index:1,evidence:{source:'synthetic'},
};

beforeEach(()=>useKeywordStore.setState({skus:[],keywords:{},entries:[],analyses:[]}));

it('restores a blocked frozen run without fabricating scores, bids or Exact/Broad',()=>{
  useKeywordStore.getState().upsertProductSku({id:run.product_id,sku:'SYNTHETIC',name:'Fixture',
    material:'',uses:[],storeIds:[],hasLibrary:false});
  useKeywordStore.getState().installServerRun(run.product_id,run,[result]);
  const state=useKeywordStore.getState();
  expect(state.entries[0]).toMatchObject({score:null,grade:'复查',exact:false,broad:false,
    suggestedBid:null,analysisVersion:run.rule_version_id});
  expect(state.analyses[0].runId).toBe(run.run_id);
  expect(state.keywords[result.term_id].monthlySearches).toBeNull();
});
