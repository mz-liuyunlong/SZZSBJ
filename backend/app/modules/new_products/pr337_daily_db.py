"""PR337 bounded daily source-to-snapshot plan and guarded persistence.

Production only for apply; dry run is READ ONLY. A single PostgreSQL
transaction serializes the task and rechecks each mutable row. No upstream
MART/FACT writes, no user approvals/market score writes, no cross-SKU joins.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import rules
from .pr337_daily_core import VERSION, compute, natural, numeric, to_date

LOG = logging.getLogger(__name__)
LA = ZoneInfo('America/Los_Angeles')
MAX_PRODUCTS = 5000
BATCH = 150
MAX_DAILY_ROWS = 3000
TAG = '[{"label":"小批量测品"}]'

_CANDIDATES = text('''
SELECT s.source_account_ref AS account, s.store_id AS store, s.item_id AS item,
       s.local_sku AS sku, s.msku AS msku, s.local_name AS product_name,
       s.store_name AS store_name, s.title AS title, s.picture_url AS image_url,
       s.owner_ref AS owner_name, s.category AS category_l2,
       s.listing_start_at_utc AS listing_start,
       s.product_tags_json @> CAST(:tag AS jsonb) AS is_tagged,
       r.id::text AS registry_id, r.is_currently_tagged AS registered_tag,
       p.registry_id IS NOT NULL AS has_performance,
       p.first_wfs_available_date_la AS saved_start,
       p.metric_window_start_la AS saved_begin,
       p.metric_window_end_la AS saved_end,
       p.first_order_date_la AS saved_first,
       p.sales_orders AS saved_orders, p.sales_units AS saved_units,
       p.updated_at AS saved_updated, p.data_coverage_json AS coverage,
       p.score AS final_score, p.grade AS final_grade,
       p.process_status AS process_status,
       p.rule_version_id::text AS saved_rule_id,
       l.first_wfs_available_date_la AS locked_start,
       t.final_result AS final_result,
       EXISTS (SELECT 1 FROM biz_new_product_purchase_applications a
         WHERE a.source_account_ref=s.source_account_ref AND a.store_id=s.store_id
           AND a.item_id=s.item_id AND a.status IN ('submitted','approved')) AS purchase_protected,
       EXISTS (SELECT 1 FROM biz_new_product_tracking_decisions d
         WHERE d.source_account_ref=s.source_account_ref AND d.store_id=s.store_id
           AND d.item_id=s.item_id AND d.decision IN ('打品成功','打品失败')) AS decision_protected,
       EXISTS (SELECT 1 FROM biz_new_product_tracking_review_applications a
         WHERE a.registry_id=r.id AND a.status IN ('submitted','approved')) AS review_protected
FROM mart_listing_management_current s
LEFT JOIN biz_new_product_registry r
 ON r.source_account_ref=s.source_account_ref
 AND r.store_id=s.store_id AND r.item_id=s.item_id
LEFT JOIN biz_new_product_performance_current p ON p.registry_id=r.id
LEFT JOIN listing_wfs_first_stock_la_locked l
 ON l.source_account_ref=s.source_account_ref
 AND l.store_id=s.store_id AND l.item_id=s.item_id
LEFT JOIN biz_new_product_tracking_current t ON t.registry_id=r.id
WHERE s.product_tags_json @> CAST(:tag AS jsonb)
ORDER BY s.source_account_ref,s.store_id,s.item_id
LIMIT :limit
''')

_MART = text('''
WITH wants AS (
 SELECT idx,account,store,item,begin_day,end_day
 FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(idx text,account text,store text,item text,begin_day date,end_day date)
)
SELECT w.idx, d.business_date_la AS day,
       sum(d.order_count) AS orders, sum(d.sales_qty) AS units,
       count(*) FILTER (WHERE d.order_count IS NULL OR d.sales_qty IS NULL
          OR d.order_count < 0 OR d.sales_qty < 0
          OR d.order_count <> trunc(d.order_count)
          OR d.sales_qty <> trunc(d.sales_qty)) AS bad_rows,
       sum(d.sales_amount) AS revenue,
       count(*) FILTER (WHERE d.sales_amount IS NULL
          OR d.sales_currency_code IS DISTINCT FROM 'USD') AS revenue_bad,
       sum(d.gross_profit_amount) AS profit,
       sum(d.purchase_cost_total_usd) AS purchase,
       sum(d.first_leg_cost_total_usd) AS freight,
       count(*) FILTER (WHERE d.cost_status IS DISTINCT FROM 'complete'
          OR d.gross_profit_amount IS NULL OR d.sales_amount IS NULL
          OR d.purchase_cost_total_usd IS NULL OR d.first_leg_cost_total_usd IS NULL
          OR d.sales_currency_code IS DISTINCT FROM 'USD'
          OR d.gross_profit_currency_code IS DISTINCT FROM 'USD') AS profit_bad
FROM wants w
JOIN mart_daily_sales_item_day d
 ON d.source_account_ref=w.account AND d.store_id=w.store AND d.item_id=w.item
 AND d.business_date_la BETWEEN w.begin_day AND w.end_day
GROUP BY w.idx,d.business_date_la
ORDER BY w.idx,d.business_date_la LIMIT :row_limit
''')

_ADS = text('''
WITH wants AS (
 SELECT idx,account,store,item,begin_day,end_day
 FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
 AS j(idx text,account text,store text,item text,begin_day date,end_day date)
)
SELECT w.idx, a.business_date_la AS day,
 sum(a.ad_spend_amount) AS spend,
 sum(a.num_ads_clicks) AS clicks,
 sum(a.attributed_orders) AS orders,
 sum(a.attributed_sales_amount) AS sales,
 count(*) FILTER (WHERE a.ad_spend_amount IS NULL OR a.num_ads_clicks IS NULL
   OR a.attributed_orders IS NULL OR a.attributed_sales_amount IS NULL
   OR a.ad_spend_amount < 0 OR a.num_ads_clicks < 0 OR a.attributed_orders < 0
   OR a.ad_spend_currency_code IS DISTINCT FROM 'USD'
   OR (nullif(btrim(a.attributed_sales_currency_code),'') IS NOT NULL
       AND btrim(a.attributed_sales_currency_code) <> 'USD')) AS bad_rows
FROM wants w
JOIN fact_walmart_ad_item_sp_daily a
 ON a.source_account_ref=w.account AND a.store_id=w.store AND a.item_id=w.item
 AND a.business_date_la BETWEEN w.begin_day AND w.end_day
GROUP BY w.idx,a.business_date_la
ORDER BY w.idx,a.business_date_la LIMIT :row_limit
''')

_WATERMARKS = text('''
WITH wanted AS (
 SELECT account,store FROM jsonb_to_recordset(CAST(:stores AS jsonb))
 AS j(account text,store text)
)
SELECT w.account,w.store,max(d.business_date_la) AS newest_day
FROM wanted w
LEFT JOIN mart_daily_sales_item_day d
 ON d.source_account_ref=w.account AND d.store_id=w.store
 AND d.business_date_la BETWEEN :floor_day AND :cutoff
GROUP BY w.account,w.store
''')

_RULE = text('''
SELECT id::text AS id, version, config_json AS config
FROM biz_new_product_rule_versions WHERE kind='performance'
ORDER BY version DESC LIMIT 1
''')

_INSERT_REG = text('''
INSERT INTO biz_new_product_registry
(id, source_account_ref, store_id, item_id, listing_source_tag,
 is_currently_tagged, sku, msku, product_name, store_name, owner_name,
 image_url, category_l2, listing_date_la, updated_at, last_source_seen_at)
VALUES (CAST(:id AS uuid),:account,:store,:item,'小批量测品',TRUE,
 :sku,:msku,:product_name,:store_name,:owner_name,
 :image_url,:category_l2,:listing_date_la,now(),now())
ON CONFLICT (source_account_ref,store_id,item_id) DO NOTHING
''')

_INSERT_PERF = text('''
INSERT INTO biz_new_product_performance_current
(registry_id, first_wfs_available_date_la, metric_window_start_la,
 metric_window_end_la, data_status, data_coverage_json, updated_at)
VALUES (CAST(:id AS uuid),:first_wfs,:start,:end,:data_status,
 CAST(:coverage AS jsonb),now())
ON CONFLICT (registry_id) DO NOTHING
''')

_UPDATE = text('''
UPDATE biz_new_product_performance_current p
SET first_wfs_available_date_la=:first_wfs,
    first_order_date_la=:first_order,
    metric_window_start_la=:start,metric_window_end_la=:end,
    sales_orders=:orders,sales_units=:units,
    sales_amount_usd=:revenue,profit_usd=:profit,
    roi=:roi, profit_margin_pct=:margin,
    ad_spend_usd=:ad_spend,ad_clicks=:ad_clicks,ad_sales_usd=:ad_sales,
    acos_pct=:acos,ad_spend_ratio_pct=:ad_ratio,
    rule_version_id=CAST(:rule_id AS uuid),
    data_coverage_json=CAST(:coverage AS jsonb),data_status=:data_status,
    calculated_at=now(),updated_at=now()
WHERE p.registry_id=CAST(:id AS uuid)
 AND p.updated_at IS NOT DISTINCT FROM :old_updated
 AND p.data_coverage_json IS NOT DISTINCT FROM CAST(:old_coverage AS jsonb)
 AND p.score IS NULL AND p.grade IS NULL
 AND (p.process_status IS NULL OR p.process_status IN
      ('观察期','待评分','待评估','未完成','new','active','evaluating'))
 AND NOT EXISTS(SELECT 1 FROM biz_new_product_tracking_current t
                WHERE t.registry_id=p.registry_id AND t.final_result IS NOT NULL)
 AND NOT EXISTS(SELECT 1 FROM biz_new_product_purchase_applications a
   JOIN biz_new_product_registry r ON r.id=p.registry_id
   WHERE a.source_account_ref=r.source_account_ref AND a.store_id=r.store_id
    AND a.item_id=r.item_id AND a.status IN ('submitted','approved'))
 AND NOT EXISTS(SELECT 1 FROM biz_new_product_tracking_decisions d
   JOIN biz_new_product_registry r ON r.id=p.registry_id
   WHERE d.source_account_ref=r.source_account_ref AND d.store_id=r.store_id
    AND d.item_id=r.item_id AND d.decision IN ('打品成功','打品失败'))
 AND NOT EXISTS(SELECT 1 FROM biz_new_product_tracking_review_applications a
   WHERE a.registry_id=p.registry_id AND a.status IN ('submitted','approved'))
 AND EXISTS (SELECT 1 FROM biz_new_product_registry r
   JOIN mart_listing_management_current l
    ON l.source_account_ref=r.source_account_ref AND l.store_id=r.store_id
    AND l.item_id=r.item_id
   WHERE r.id=p.registry_id AND l.product_tags_json @> CAST(:tag AS jsonb))
''')


def batches(seq, size=BATCH):
    for i in range(0,len(seq),size):
        yield seq[i:i+size]


def guarded(row: Mapping[str, Any]) -> str | None:
    if row.get('final_score') is not None or row.get('final_grade') is not None:
        return 'PUBLISHED_SCORE_PROTECTED'
    if row.get('final_result') is not None:
        return 'FINAL_TRACKING_PROTECTED'
    if any(row.get(k) for k in ('purchase_protected','decision_protected','review_protected')):
        return 'APPROVAL_PROTECTED'
    if row.get('process_status') not in (None,'观察期','待评分','待评估','未完成','new','active','evaluating'):
        return 'UNKNOWN_STATUS_PROTECTED'
    return None


def _json(value):
    return json.dumps(value,ensure_ascii=False,default=str,sort_keys=True,separators=(',',':'))


def plan(row: Mapping[str, Any], proof: dict | None, config_id: str | None) -> dict | None:
    """Fails closed on changed WFS or same-window MART totals mismatch."""
    if (reason:=guarded(row)):
        raise ValueError(reason)
    locked = to_date(row.get('locked_start'))
    old_start = to_date(row.get('saved_start'))
    if old_start is not None and locked != old_start:
        raise ValueError('WFS_LOCK_CHANGED_REVIEW')
    old_coverage = row.get('coverage')
    if old_coverage is not None and not isinstance(old_coverage,dict):
        raise ValueError('COVERAGE_INVALID')
    coverage = json.loads(_json(old_coverage or {}))
    if proof is None:
        if row.get('has_performance'):
            return None
        return {
            'status':'awaiting_wfs' if locked is None else 'awaiting_mart',
            'coverage':{}, 'first_wfs':locked, 'end':None,
        }
    start, end=to_date(proof['window_start_la']),to_date(proof['window_end_la'])
    saved_begin=to_date(row.get('saved_begin'))
    saved_end=to_date(row.get('saved_end'))
    saved_first=to_date(row.get('saved_first'))
    if (saved_first is not None and saved_begin==start and saved_end==end
        and saved_first!=to_date(proof.get('first_order_date'))):
        raise ValueError('SAVED_FIRST_ORDER_DISAGREES')
    if (old_start is not None and old_start!=start) or (
        saved_begin==start and saved_end==end and row.get('saved_orders') is not None and
        (natural(row.get('saved_orders'))!=proof['orders'] or
         numeric(row.get('saved_units'))!=Decimal(proof['units']))
    ):
        raise ValueError('SAVED_MART_TOTALS_DISAGREE')
    prev_auto=coverage.get('auto_dimension_scores')
    if prev_auto is not None and not isinstance(prev_auto,dict):
        raise ValueError('AUTO_SCORE_BLOCK_INVALID')
    dimension_block={
        'scoring_provenance': VERSION, 'rule_version': proof['rule_version'],
        'dimensions':proof['dimensions'],
        'automatic_points':proof['automatic_points'],
        'covered_weight_pct':proof['covered_weight_pct'],
        'cutoff_la':proof['cutoff_la'],
        'window_start_la':proof['window_start_la'],
        'window_end_la':proof['window_end_la'],
        'observation_state':'in_progress' if not proof['observation_complete'] else 'complete',
        'missing':[k for k,v in proof['dimensions'].items() if v is None],
    }
    proof_save={k:v for k,v in proof.items() if k!='dimensions'}
    # Never rewrite the original evidence of an earlier one-shot rebuild.
    if 'pr337_daily_original_auto_v1' not in coverage and isinstance(prev_auto,dict):
        coverage['pr337_daily_original_auto_v1']=prev_auto
        coverage['pr337_daily_original_window_v1']={
            k:str(row.get(k)) if row.get(k) is not None else None for k in
            ('saved_start','saved_begin','saved_end','saved_orders','saved_units','saved_first')
        }
    coverage['auto_dimension_scores']=dimension_block
    coverage['pr337_daily_verified_v1']=proof_save
    fp=hashlib.sha256(_json({'block':dimension_block,'proof':proof_save,'rule_id':config_id}).encode()).hexdigest()
    coverage['pr337_daily_fingerprint_v1']=fp
    if (isinstance(old_coverage,dict) and old_coverage.get('pr337_daily_fingerprint_v1')==fp
        and str(row.get('saved_rule_id') or '')==str(config_id or '')
        and saved_begin==start and saved_end==end):
        return None
    finished_and_complete=(proof['observation_complete'] and
        all(proof['dimensions'].get(k) is not None for k in ('speed','ad','profit','trust')))
    return {'status':'available' if finished_and_complete else 'partial',
            'coverage':coverage,'proof':proof,'first_wfs':start,'end':end}


def _config(session: Session) -> tuple[str|None,int,dict]:
    raw=session.execute(_RULE).mappings().first()
    if raw is not None:
        config=dict(raw['config'])
        rules.validate('performance',config)
        if int(config['confirmedScoring']['speed']['observationDays']) != 14:
            raise RuntimeError('PR337_WINDOW_RULE_REQUIRES_OWNER_REVIEW')
        return raw['id'],int(raw['version']),config
    # Preserve established defaults, but never manufacture a final grade.
    return None,0,{'weights':rules.DEFAULT_WEIGHTS,'confirmedScoring':rules.DEFAULT_PARAMETERS}


def run_daily(session:Session,*,apply:bool=False,cutoff_la:date|None=None)->dict:
    cutoff_la=cutoff_la or datetime.now(LA).date()-timedelta(days=1)
    if not isinstance(cutoff_la,date) or cutoff_la>datetime.now(LA).date():
        raise ValueError('CUTOFF_INVALID')
    if apply:
        obtained=session.scalar(text("SELECT pg_try_advisory_xact_lock(hashtext('PR337_DAILY_PERSIST_V1'))"))
        if obtained is not True:
            raise RuntimeError('PR337_DAILY_LOCK_BUSY')
    candidates=[dict(r) for r in session.execute(_CANDIDATES,{'tag':TAG,'limit':MAX_PRODUCTS+1}).mappings()]
    if len(candidates)>MAX_PRODUCTS:
        raise RuntimeError('CANDIDATE_LIMIT_EXCEEDED')
    if not candidates:
        raise RuntimeError('NO_TAGGED_ITEMS_STOP')
    cfg_id,cfg_version,cfg=_config(session)
    wants=[]
    for idx,c in enumerate(candidates):
        c['_idx']=str(idx)
        start=to_date(c.get('locked_start'))
        if start is not None and start<=cutoff_la:
            wants.append({'idx':str(idx),'account':c['account'],'store':c['store'],'item':c['item'],
                          'begin_day':start.isoformat(),'end_day':min(start+timedelta(days=13),cutoff_la).isoformat()})
    marts=defaultdict(list)
    ads=defaultdict(list)
    for group in batches(wants):
        as_json=_json(group)
        ms=list(session.execute(_MART,{'wanted':as_json,'row_limit':MAX_DAILY_ROWS+1}).mappings())
        aa=list(session.execute(_ADS,{'wanted':as_json,'row_limit':MAX_DAILY_ROWS+1}).mappings())
        if len(ms)>MAX_DAILY_ROWS or len(aa)>MAX_DAILY_ROWS:
            raise RuntimeError('SOURCE_BATCH_LIMIT_EXCEEDED')
        for r in ms: marts[r['idx']].append(dict(r))
        for r in aa: ads[r['idx']].append(dict(r))
    stores=sorted({(c['account'],c['store']) for c in candidates})
    watermark={}
    for group in batches(stores):
        payload=_json([{'account':a,'store':s} for a,s in group])
        recs=session.execute(_WATERMARKS,{'stores':payload,
            'floor_day':cutoff_la-timedelta(days=7),'cutoff':cutoff_la}).mappings()
        watermark.update({(x['account'],x['store']):to_date(x['newest_day']) for x in recs})
    outcomes=Counter()
    examples=[]
    for c in candidates:
        try:
            if reason:=guarded(c):
                raise ValueError(reason)
            start=to_date(c.get('locked_start'))
            current_end=min(start+timedelta(days=13),cutoff_la) if start and start<=cutoff_la else None
            if current_end is not None:
                mature=watermark.get((c['account'],c['store']))
                # Mature completed windows older than 7 days can be verified
                # against immutable existing 14-day totals even if store is now quiet.
                old_finished=(c.get('saved_orders') is not None and
                     to_date(c.get('saved_begin'))==start and
                     to_date(c.get('saved_end'))==current_end and
                     current_end <= cutoff_la-timedelta(days=7))
                historically_mature=(current_end<=cutoff_la-timedelta(days=7))
                if not (historically_mature or old_finished) and (mature is None or mature<current_end):
                    # For a newly tagged product without mature data, create only
                    # an awaiting_mart record; never publish provisional scores.
                    if c.get('registry_id') is None and not c.get('has_performance'):
                        current_end=None
                    else:
                        raise ValueError('STORE_MART_WATERMARK_PENDING')
            proof=None
            if current_end is not None and marts.get(c['_idx']):
                proof=compute(first_wfs=start,cutoff=current_end,mart=marts[c['_idx']],
                              ads=ads.get(c['_idx'],[]),config=cfg,rule_version=cfg_version)
            result=plan(c,proof,cfg_id)
            if result is None:
                if c.get('registered_tag') is False:
                    if apply:
                        changed=session.execute(text('''UPDATE biz_new_product_registry SET
                          is_currently_tagged=TRUE,updated_at=now() WHERE
                          id=CAST(:id AS uuid) AND is_currently_tagged=FALSE'''),
                          {'id':c['registry_id']}).rowcount
                        if changed != 1:
                            raise RuntimeError('REGISTRY_RETAG_CONFLICT_ABORT')
                    outcomes['retagged' if apply else 'would_retag']+=1
                else:
                    outcomes['unchanged']+=1
                continue
            if len(examples)<15:
                p=result.get('proof')
                examples.append({'store':c['store'],'item':c['item'],'sku':c['sku'],
                    'status':result['status'],
                    'orders':p['orders'] if p else None,'units':p['units'] if p else None,
                    'speed':p['dimensions']['speed'] if p else None,
                    'trust':p['dimensions']['trust'] if p else None})
            if not apply:
                outcomes['would_write']+=1
                continue
            rg_id=c.get('registry_id') or str(uuid4())
            if not c.get('registry_id'):
                for field,cap in (('sku',128),('msku',128),('store_name',255),('owner_name',255)):
                    if isinstance(c.get(field),str) and len(c[field])>cap:
                        raise ValueError('REGISTRY_FIELD_TOO_LONG_'+field)
                inserted=session.execute(_INSERT_REG,{
                    'id':rg_id,'account':c['account'],'store':c['store'],'item':c['item'],
                    'sku':c['sku'],'msku':c['msku'],
                    'product_name':c['product_name'] or c['title'],
                    'store_name':c['store_name'],'owner_name':c['owner_name'],
                    'image_url':c['image_url'],'category_l2':c['category_l2'],
                    'listing_date_la':c['listing_start'].astimezone(LA).date()
                        if isinstance(c.get('listing_start'),datetime)
                        and c['listing_start'].tzinfo is not None else None,
                }).rowcount
                if inserted != 1:
                    raise RuntimeError('REGISTRY_CONFLICT_ABORT')
                outcomes['registry_created']+=1
            elif c.get('registered_tag') is False:
                session.execute(text('''UPDATE biz_new_product_registry SET
                      is_currently_tagged=TRUE,updated_at=now()
                      WHERE id=CAST(:id AS uuid) AND is_currently_tagged=FALSE'''),{'id':rg_id})
            if not c.get('has_performance'):
                inserted=session.execute(_INSERT_PERF,{
                    'id':rg_id,'first_wfs':result.get('first_wfs'),
                    'start':result.get('first_wfs') if result.get('proof') else None,
                    'end':result.get('end'),'data_status':result['status'],
                    'coverage':_json({}),
                }).rowcount
                if inserted!=1:
                    raise RuntimeError('PERFORMANCE_CONFLICT_ABORT')
                outcomes['performance_created']+=1
            if proof is None:
                outcomes['awaiting_evidence']+=1
                continue
            ad_spend=numeric(proof.get('ad_spend_usd'))
            ad_sales=numeric(proof.get('ad_sales_usd'))
            revenue=numeric(proof.get('sales_amount_usd'))
            acos=ad_spend/ad_sales*100 if ad_spend is not None and ad_sales is not None and ad_sales>0 else None
            ratio=ad_spend/revenue*100 if ad_spend is not None and revenue is not None and revenue>0 else None
            upd={
                'id':rg_id,'first_wfs':start,'first_order':to_date(proof.get('first_order_date')),
                'start':start,'end':to_date(proof['window_end_la']),
                'orders':proof['orders'],'units':proof['units'],
                'revenue':revenue,'profit':numeric(proof.get('profit_usd')),
                'roi':numeric(proof.get('roi')),'margin':numeric(proof.get('margin_pct')),
                'ad_spend':ad_spend,'ad_clicks':proof['ad_clicks'],'ad_sales':ad_sales,
                'acos':acos,'ad_ratio':ratio,
                'rule_id':cfg_id,'coverage':_json(result['coverage']),
                'data_status':result['status'],
                'old_updated':c.get('saved_updated') if c.get('has_performance') else session.scalar(
                     text('SELECT updated_at FROM biz_new_product_performance_current WHERE registry_id=CAST(:id AS uuid)'),{'id':rg_id}),
                'old_coverage':(_json(c.get('coverage')) if c.get('coverage') is not None else None)
                    if c.get('has_performance') else _json({}),
                'tag':TAG,
            }
            done=session.execute(_UPDATE,upd).rowcount
            if done!=1:
                raise RuntimeError('STALE_OR_FROZEN_ROW_ABORT')
            outcomes['written']+=1
        except ValueError as e:
            outcomes[str(e)]+=1
    return {'status':'applied' if apply else 'dry_run','version':VERSION,
      'cutoff_la':cutoff_la.isoformat(),'candidates':len(candidates),
      'outcomes':dict(sorted(outcomes.items())), 'examples':examples}
