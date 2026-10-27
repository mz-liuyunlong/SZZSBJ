import {listKeywordRuleSets,listKeywordRuleVersions,type KeywordRuleSet,type KeywordRuleVersion} from '@/api/keywordPlanningV11Api';
import type {RuleConfig} from './types';

export const SYSTEM_DEFAULT_RULE_KEY='keyword_v11_internal_default';

export function selectEffectiveRule(rows:Array<{ruleSet:KeywordRuleSet;version:KeywordRuleVersion}>,account:string){
 return rows.filter(({ruleSet,version})=>ruleSet.is_enabled&&version.status==='published'
   &&(ruleSet.scope_key===account||(ruleSet.scope_key==='global'&&ruleSet.rule_key===SYSTEM_DEFAULT_RULE_KEY)))
   .sort((a,b)=>Number(b.ruleSet.scope_key===account)-Number(a.ruleSet.scope_key===account)
     ||(b.version.published_at??'').localeCompare(a.version.published_at??'')
     ||b.version.version_number-a.version.version_number
     ||b.version.version_id.localeCompare(a.version.version_id))[0]??null;
}

export async function loadEffectiveRule(account:string){
 const sets=await listKeywordRuleSets(account);
 const versions=await Promise.all(sets.filter(row=>row.is_enabled).map(async ruleSet=>(
   (await listKeywordRuleVersions(account,ruleSet.rule_set_id)).map(version=>({ruleSet,version}))
 )));
 return selectEffectiveRule(versions.flat(),account);
}

export function displayRule(version:KeywordRuleVersion):RuleConfig|null{
 const value=version.config.editor_config;
 if(!value||typeof value!=='object'||Array.isArray(value))return null;
 const rule=value as RuleConfig;
 return rule.weights&&rule.thresholds&&rule.limits&&rule.asin&&rule.bid&&rule.naming&&rule.listing&&rule.export
   ?{...rule,version:version.version_number}:null;
}
