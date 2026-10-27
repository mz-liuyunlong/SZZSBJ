/** Walmart keyword V1.1: ONLY persisted runs, unapproved output is INTERNAL. */
import { backendDownload, backendRequest } from '@/api/backendApi';

export type KeywordRunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'blocked';
export interface KeywordRun {
  run_id: string;
  product_id: string;
  source_account_ref: string;
  item_id: string;
  status: KeywordRunStatus;
  rule_version_id: string;
  created_at: string;
  finished_at: string | null;
  keyword_count: number;
}
export interface KeywordRunList { items: KeywordRun[]; total: number; limit: number; offset: number }
export interface KeywordResult {
  term_id: string;
  keyword: string;
  primary_type: string | null;
  page_coverage: string | null;
  core_root: string | null;
  score: number | null;
  match_points: number | null;
  intent_points: number | null;
  page_points: number | null;
  root_points: number | null;
  data_points: number | null;
  risk_points: number | null;
  base_grade: string | null;
  allocation_grade: string | null;
  exact_selected: boolean;
  broad_selected: boolean;
  broad_role: string | null;
  suggested_optimization_bid: string | number | null;
  decision_status: string;
  risk_reasons: string[];
  exact_reason: string | null;
  broad_reason: string | null;
  quality_note: string | null;
  rank_index: number | null;
  evidence: Record<string, unknown>;
}
export interface KeywordResultList {
  run_id: string;
  items: KeywordResult[];
  total: number;
  limit: number;
  offset: number;
  official_export_authorized: false;
}
export interface CreateKeywordAnalysisRequest {
  source_account_ref: string;
  product_id: string;
  item_id: string;
  product_fact_snapshot_id: string;
  rule_version_id: string;
  upload_file_id: string;
  request_key: string;
  selected_asins?: string[];
}
export interface CreateKeywordAnalysisResult {
  run_id: string;
  status: KeywordRunStatus;
  created: boolean;
  keyword_count: number;
  official_export_authorized: false;
}
const API = '/api/v1/keyword-planning';
const query = (account: string, extras: Record<string, string | number> = {}) => {
  const params = new URLSearchParams({source_account_ref: account});
  Object.entries(extras).forEach(([key, value]) => params.set(key, String(value)));
  return params.toString();
};
export const listKeywordRuns = async (
  productId: string, account: string, limit = 20, offset = 0,
): Promise<KeywordRunList> =>
  (await backendRequest<KeywordRunList>(
    `${API}/products/${encodeURIComponent(productId)}/runs?${query(account, {limit, offset})}`,
  )).data;

export const getKeywordRun = async (runId: string, account: string): Promise<KeywordRun> =>
  (await backendRequest<KeywordRun>(
    `${API}/runs/${encodeURIComponent(runId)}?${query(account)}`,
  )).data;

export const listRunKeywords = async (
  runId: string, account: string, limit = 100, offset = 0,
): Promise<KeywordResultList> =>
  (await backendRequest<KeywordResultList>(
    `${API}/runs/${encodeURIComponent(runId)}/keywords?${query(account, {limit, offset})}`,
  )).data;

export async function loadAllRunKeywords(runId: string, account: string): Promise<KeywordResult[]> {
  const items: KeywordResult[] = [];
  for (let offset = 0; offset < 12000; offset += 200) {
    const page = await listRunKeywords(runId, account, 200, offset);
    items.push(...page.items);
    if (items.length >= page.total) return items;
  }
  throw new Error('分析结果超过页面安全上限');
}

export const createKeywordAnalysis = async (
  input: CreateKeywordAnalysisRequest,
): Promise<CreateKeywordAnalysisResult> =>
  (await backendRequest<CreateKeywordAnalysisResult>(`${API}/analyses`, {
    method: 'POST', body: JSON.stringify(input),
  })).data;

export const downloadKeywordInternalWorkbook = async (
  runId: string, account: string,
): Promise<void> => backendDownload(
  `${API}/runs/${encodeURIComponent(runId)}/internal-workbook?${query(account)}`,
  `kw_internal_${runId}.xlsx`,
);

/** Read-only four-sheet review. Does not authorize Walmart Bulk upload. */
export const downloadKeywordAiReviewWorkbook = async (
  jobId: string, account: string,
): Promise<void> => backendDownload(
  `${API}/ai-tasks/${encodeURIComponent(jobId)}/four-sheet-workbook?${query(account)}`,
  `kw_ai_review_${jobId}.xlsx`,
);

/** Strictly do not enable an official-upload button based on this API. */
export const canOfficiallyUploadV11 = (): false => false;

export interface KeywordSourceUploadResult {
  upload_id: string;
  status: 'parsed' | 'failed';
  source_rows: number;
}

/** Binary XLSX import (not multipart): requires backend opt-in and private store. */
export const uploadKeywordSourceXlsx = async (
  file: File, account: string, productId: string, verifiedFactId: string,
): Promise<KeywordSourceUploadResult> => {
  const params = new URLSearchParams({
    source_account_ref: account,
    product_id: productId,
    product_fact_snapshot_id: verifiedFactId,
    filename: file.name,
  });
  return (await backendRequest<KeywordSourceUploadResult>(
    `${API}/imports/xlsx?${params.toString()}`,
    { method: 'POST', headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }, body: file },
  )).data;
};

export interface KeywordPreflight {
  source_account_ref: string;
  product_id: string;
  rule_version_id: string;
  can_create_review_run: boolean;
  can_generate_scored_results: boolean;
  can_generate_official_upload: false;
  candidate_count: number;
  automatic_evidence_count: number;
  reviewed_evidence_count: number;
  manual_review_count: number;
  top40_review_required: number;
  review_reason_codes: string[];
}

export interface KeywordRuleSet {
  rule_set_id: string;
  rule_key: string;
  display_name: string;
  scope_key: string;
  is_enabled: boolean;
}

export interface KeywordRuleVersion {
  version_id: string;
  version_number: number;
  status: 'draft' | 'published' | 'retired';
  config_sha256: string;
  config: Record<string, unknown>;
  created_at: string | null;
  published_at: string | null;
  publish_eligible: boolean;
}

export interface KeywordVersionReceipt {
  version_id: string;
  rule_set_id: string;
  version_number: number;
  status: 'draft' | 'published' | 'retired';
  config_sha256: string;
  publish_eligible: false;
}

export interface KeywordDraftLimits {
  max_p0: number;
  max_p1: number;
  max_p2: number;
  max_exact: number;
  max_broad_roots: number;
  max_broad_long_tails: number;
}

export const DEFAULT_DRAFT_LIMITS: KeywordDraftLimits = {
  max_p0: 5, max_p1: 10, max_p2: 30,
  max_exact: 20, max_broad_roots: 5, max_broad_long_tails: 15,
};

export const preflightKeywordAnalysis = async (
  input: Omit<CreateKeywordAnalysisRequest, 'request_key'>,
): Promise<KeywordPreflight> => {
  const params = new URLSearchParams(query(input.source_account_ref, {
      product_id: input.product_id,
      item_id: input.item_id,
      product_fact_snapshot_id: input.product_fact_snapshot_id,
      rule_version_id: input.rule_version_id,
      upload_file_id: input.upload_file_id,
    }));
  input.selected_asins?.forEach(asin=>params.append('selected_asins',asin));
  return (await backendRequest<KeywordPreflight>(`${API}/preflight?${params.toString()}`)).data;
};

export const listKeywordRuleSets = async (account: string): Promise<KeywordRuleSet[]> =>
  (await backendRequest<{items: KeywordRuleSet[]; total: number}>(
    `${API}/rulesets?${query(account)}`,
  )).data.items;

export const listKeywordRuleVersions = async (
  account: string, ruleSetId: string,
): Promise<KeywordRuleVersion[]> =>
  (await backendRequest<{items: KeywordRuleVersion[]; total: number}>(
    `${API}/rulesets/${encodeURIComponent(ruleSetId)}/versions?${query(account)}`,
  )).data.items;

export const createKeywordRuleDraft = async (
  account: string, ruleSetId: string, limits: KeywordDraftLimits,
  editorConfig: Record<string, unknown> = {},
): Promise<KeywordVersionReceipt> =>
  (await backendRequest<KeywordVersionReceipt>(
    `${API}/rulesets/${encodeURIComponent(ruleSetId)}/drafts`,
    { method: 'POST', body: JSON.stringify({
      source_account_ref: account,
      limits, confirmed_brands: {}, suspected_brands: {}, editor_config: editorConfig,
    }) },
  )).data;

export const createKeywordRuleSet = async (account: string): Promise<{rule_set_id:string}> =>
  (await backendRequest<{rule_set_id:string}>(`${API}/rulesets`, {
    method:'POST', body:JSON.stringify({source_account_ref:account,rule_key:'keyword_v11_ui',display_name:'Walmart 关键词 V1.1'}),
  })).data;

export const saveKeywordRuleDraft = async (
  account:string, versionId:string, limits:KeywordDraftLimits, editorConfig:Record<string,unknown>,
):Promise<KeywordVersionReceipt> =>
  (await backendRequest<KeywordVersionReceipt>(`${API}/rules/${encodeURIComponent(versionId)}/draft`, {
    method:'PATCH',body:JSON.stringify({source_account_ref:account,limits,
      confirmed_brands:{},suspected_brands:{},editor_config:editorConfig}),
  })).data;

export interface KeywordRuleDecision {
  decision_key: string;
  status: 'pending_review' | 'approved' | 'rejected';
  proposal: Record<string, unknown>;
  evidence_ref: string;
  submitted_by: string;
  reviewed_by: string | null;
  config_sha256: string;
}
export interface KeywordDecisionEvent {
  decision_id: string;
  action: string;
  actor: string;
  status_after: string;
  evidence_ref: string;
}
export const listKeywordRuleDecisions = async (account: string, versionId: string) =>
  (await backendRequest<{items: KeywordRuleDecision[]; events: KeywordDecisionEvent[]; total: number}>(
    `${API}/rules/${encodeURIComponent(versionId)}/decisions?${query(account)}`,
  )).data;
export const submitKeywordRuleDecision = async (
  account: string, versionId: string, decisionKey: string, proposal: Record<string, unknown>, evidenceRef: string,
) => (await backendRequest<{decision_id: string; status: string}>(
  `${API}/rules/${encodeURIComponent(versionId)}/decisions/${decisionKey}/submit`,
  {method: 'POST', body: JSON.stringify({source_account_ref: account, proposal, evidence_ref: evidenceRef})},
)).data;
export const reviewKeywordRuleDecision = async (
  account: string, versionId: string, decisionKey: string, approved: boolean, evidenceRef: string,
) => (await backendRequest<{decision_key: string; status: string}>(
  `${API}/rules/${encodeURIComponent(versionId)}/decisions/${decisionKey}/review`,
  {method: 'POST', body: JSON.stringify({source_account_ref: account, approved, evidence_ref: evidenceRef})},
)).data;
export const publishKeywordRuleVersion = async (account: string, versionId: string) =>
  (await backendRequest<KeywordVersionReceipt>(`${API}/rules/${encodeURIComponent(versionId)}/publish`,
    {method:'POST', body:JSON.stringify({source_account_ref:account})})).data;
export const retireKeywordRuleVersion = async (account: string, versionId: string) =>
  (await backendRequest<KeywordVersionReceipt>(`${API}/rules/${encodeURIComponent(versionId)}/retire`,
    {method:'POST', body:JSON.stringify({source_account_ref:account})})).data;

/** Rule approval is intentionally not a browser action until D01-D08 are signed off. */
export const keywordV11BusinessDecisionsApproved = (): false => false;

export type ConfirmedKeywordField = {
  value: string;
  source: 'walmart' | 'operator' | 'product_management';
};
export interface KeywordSourceState {
  product_id: string;
  latest_confirmed_fact_id: string | null;
  latest_upload_id: string | null;
  latest_upload_filename: string | null;
  latest_upload_rows: number;
  item_id: string | null;
  confirmed_fields: Record<string, string>;
  asin_reference_count: number;
  asin_references: string[];
  source_status: 'ready_for_import' | 'fact_confirmed';
}
export interface KeywordFactConfirmation {
  source_account_ref: string;
  product_id: string;
  item_id: string;
  decodo_snapshot_id: string;
  fields: Record<string, ConfirmedKeywordField>;
  risk_boundary_mode: 'provided' | 'none';
  risk_boundary_acknowledged: boolean;
  semantic_phrases: Array<{
    phrase: string; keyword_type: string; evidence_ref: string;
    hard_risk_proven: boolean; page_phrase?: string;
  }>;
}
export interface KeywordFactReceipt {
  product_fact_snapshot_id: string;
  walmart_page_snapshot_id: string;
  status: 'confirmed';
}
export interface KeywordAsinReceipt {
  asin_snapshot_id: string;
  image_count: number;
  status: 'stored';
}
export const getKeywordSourceState = async (
  productId: string, account: string,
): Promise<KeywordSourceState> =>
  (await backendRequest<KeywordSourceState>(
    `${API}/products/${encodeURIComponent(productId)}/source-state?${query(account)}`,
  )).data;

/** Converts an existing verified Decodo snapshot; it does not call Decodo. */
export const confirmStoredKeywordFacts = async (
  input: KeywordFactConfirmation,
): Promise<KeywordFactReceipt> =>
  (await backendRequest<KeywordFactReceipt>(`${API}/sources/walmart/confirm`, {
    method: 'POST', body: JSON.stringify(input),
  })).data;

export const importStoredAsin = async (input: {
  source_account_ref: string; product_id: string; asin: string;
  decodo_snapshot_id: string;
}): Promise<KeywordAsinReceipt> =>
  (await backendRequest<KeywordAsinReceipt>(`${API}/sources/amazon/asin`, {
    method: 'POST', body: JSON.stringify(input),
  })).data;

export interface KeywordLibraryItem {
  term_id: string;
  keyword: string;
  translation: string | null;
  status: 'active' | 'review' | 'paused' | 'excluded';
  source_kinds: string[];
  source_count: number;
  observation_count: number;
  latest_grade: string | null;
  latest_score: number | null;
}
export interface KeywordLibraryRead {
  items: KeywordLibraryItem[];
  total: number;
  limit: number;
  offset: number;
  latest_run_id: string | null;
}
export const listKeywordLibrary = async (
  productId: string, account: string, filters: {
    q?: string; status?: string; source?:string; grade?:string; limit?: number; offset?: number;
  } = {},
): Promise<KeywordLibraryRead> =>
  (await backendRequest<KeywordLibraryRead>(
    `${API}/products/${encodeURIComponent(productId)}/library?${query(account, {
      q: filters.q ?? '', status: filters.status ?? 'all',
      source:filters.source??'all',grade:filters.grade??'all',
      limit: filters.limit ?? 50, offset: filters.offset ?? 0,
    })}`,
  )).data;

export interface GlobalKeywordLibraryItem {
  term_id:string; keyword:string; translation:string|null; sku_count:number;
  source_kinds:string[];
  associations:Array<{product_id:string;sku:string;status:string;grade:string|null;score:number|null;exact_selected:boolean;broad_selected:boolean}>;
}
export interface GlobalKeywordLibraryRead {
  items:GlobalKeywordLibraryItem[];total:number;limit:number;offset:number;
}
export const listGlobalKeywordLibrary = async (
  account:string, filters:{q?:string;status?:string;source?:string;grade?:string;limit?:number;offset?:number}={},
):Promise<GlobalKeywordLibraryRead> =>
  (await backendRequest<GlobalKeywordLibraryRead>(`${API}/library?${query(account,{
    q:filters.q??'',status:filters.status??'all',source:filters.source??'all',
    grade:filters.grade??'all',limit:filters.limit??50,offset:filters.offset??0,
  })}`)).data;

export const addManualKeywordWords = async (
  productId: string, input: {
    source_account_ref: string; item_id: string; request_key: string;
    words: Array<{keyword: string; translation?: string}>;
  },
): Promise<{accepted: number; source_events_created: number; status: 'review'}> =>
  (await backendRequest<{accepted: number; source_events_created: number; status: 'review'}>(
    `${API}/products/${encodeURIComponent(productId)}/library/manual`, {
      method: 'POST', body: JSON.stringify(input),
    },
  )).data;

export const updateKeywordTranslation = async (
  productId: string, termId: string, account: string, itemId: string, translation: string,
): Promise<{term_id: string; translation: string | null}> =>
  (await backendRequest<{term_id: string; translation: string | null}>(
    `${API}/products/${encodeURIComponent(productId)}/library/${encodeURIComponent(termId)}/translation`, {
      method: 'PATCH', body: JSON.stringify({
        source_account_ref: account, item_id: itemId, translation,
      }),
    },
  )).data;

/** Independently persisted async AI jobs. Existing run/result types stay unchanged. */
export interface KeywordAiJob {
  id: string;
  source_account_ref: string;
  product_id: string;
  requested_by: string;
  status: 'queued'|'running'|'succeeded'|'partial_success'|'failed'|'cancelled';
  phase: string;
  progress: number;
  total: number;
  completed: number;
  failed: number;
  run_id: string|null;
  error_code: string|null;
}
export const submitKeywordAiJob=async(input:CreateKeywordAnalysisRequest):Promise<KeywordAiJob>=>
  (await backendRequest<KeywordAiJob>(`${API}/ai-tasks`,{method:'POST',body:JSON.stringify(input)})).data;
export const listKeywordAiJobs=async(account:string):Promise<KeywordAiJob[]> =>
  (await backendRequest<{items:KeywordAiJob[];total:number}>(`${API}/ai-tasks?${query(account)}`)).data.items;
export const cancelKeywordAiJob=async(id:string,account:string):Promise<KeywordAiJob>=>
  (await backendRequest<KeywordAiJob>(`${API}/ai-tasks/${id}/cancel?${query(account)}`,{method:'POST'})).data;
export const retryKeywordAiJob=async(id:string,account:string):Promise<KeywordAiJob>=>
  (await backendRequest<KeywordAiJob>(`${API}/ai-tasks/${id}/retry?${query(account)}`,{method:'POST'})).data;

export interface KeywordAiSuggestion {
  keyword:string;
  relevance:'high'|'medium'|'low'|'review';
  risk:string;
  reason:string;
}
export const readKeywordAiSuggestions=async(jobId:string,account:string):Promise<KeywordAiSuggestion[]>=>
  (await backendRequest<{items:KeywordAiSuggestion[];total:number;advisory_only:boolean}>(
    `${API}/ai-tasks/${jobId}/results?${query(account)}`)).data.items;
