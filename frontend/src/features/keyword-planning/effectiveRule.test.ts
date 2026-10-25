import {describe,expect,it} from 'vitest';
import {selectEffectiveRule} from './effectiveRule';
import type {KeywordRuleSet,KeywordRuleVersion} from '@/api/keywordPlanningV11Api';

const version=(versionId:string,versionNumber:number,publishedAt:string):KeywordRuleVersion=>({
 version_id:versionId,version_number:versionNumber,status:'published',published_at:publishedAt,
 config_sha256:'a'.repeat(64),config:{},created_at:publishedAt,publish_eligible:false,
});
const ruleSet=(key:string,scope:string,enabled=true):KeywordRuleSet=>({
 rule_set_id:`${key}-${scope}`,rule_key:key,display_name:key,scope_key:scope,is_enabled:enabled,
});

describe('effective keyword rules',()=>{
 it('uses the persisted system baseline for a new account',()=>{
  const row={ruleSet:ruleSet('keyword_v11_internal_default','global'),version:version('default-v1',1,'2026-01-01')};
  expect(selectEffectiveRule([row],'new-account')?.version.version_id).toBe('default-v1');
 });
 it('prefers the current published account rule while ignoring drafts and disabled sets',()=>{
  const baseline={ruleSet:ruleSet('keyword_v11_internal_default','global'),version:version('default-v1',1,'2026-03-01')};
  const custom={ruleSet:ruleSet('keyword_v11_ui','acct'),version:version('account-v2',2,'2026-02-01')};
  const retired={ruleSet:ruleSet('keyword_v11_ui','acct'),version:{...version('account-v3',3,'2026-04-01'),status:'draft' as const}};
  const disabled={ruleSet:ruleSet('other','acct',false),version:version('disabled',4,'2026-05-01')};
  expect(selectEffectiveRule([baseline,custom,retired,disabled],'acct')?.version.version_id).toBe('account-v2');
  expect(selectEffectiveRule([custom],'different-account')).toBeNull();
 });
});
