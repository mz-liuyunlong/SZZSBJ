"""ONE PR337 performance result publisher, shared by daily and rule-apply triggers.

This module performs no work on import or Listing GET.  Read-only operational
source, local writable result table, and explicit publishing authorization are
separate.  Existing approved/frozen scores and existing 14-day business columns
are never silently overwritten.  Ads are one evidence group in this publisher,
not a second scheduler or a second calculation pipeline.
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import date, datetime, timedelta, UTC
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from .unified_ad_evidence import load_ad_snapshots, load_campaign_catalog

LOG = logging.getLogger(__name__)
LA = ZoneInfo('America/Los_Angeles')
BATCH = 40
Key = tuple[str, str, str]


def permission_to_write() -> bool:
    """Production requires a second explicit authorization; local is opt-in."""
    env = os.getenv('APP_ENV','').strip().lower()
    enabled = os.getenv('SZZSBJ_PR337_UNIFIED_PUBLISH_ENABLED','').strip().lower() in {
        '1','yes','true','on'
    }
    if not enabled:
        return False
    if env in {'local','dev','development'}:
        return True
    return env == 'production' and os.getenv(
        'SZZSBJ_PR337_UNIFIED_PRODUCTION_WRITE_APPROVED',''
    ).strip().lower() in {'1','yes','true','on'}


def local_target_approved(database: str | None, host: str | None) -> bool:
    # The SZZSBJ production name is szzsbj_app. Never let a local flag turn
    # an SSH tunnel to production into a writable publication target.
    return database in {'szzsbj_hybrid', 'szzsbj_dev'} and host in {
        '127.0.0.1','localhost','::1'
    }


def _eligible_rows(source: Session, item_ids: set[str] | None, limit: int) -> list[dict[str,Any]]:
    from .models import NewProductRegistry
    r = NewProductRegistry
    stmt = select(r).where(r.is_currently_tagged.is_(True))
    if item_ids is not None:
        stmt = stmt.where(r.item_id.in_(item_ids))
    if not 1 <= limit <= 500:
        raise ValueError('Limit must be between 1 and 500')
    records = source.scalars(stmt.order_by(r.source_account_ref,r.store_id,r.item_id).limit(limit+1)).all()
    if len(records)>limit:
        raise ValueError('PUBLISH_SCOPE_OVER_LIMIT: explicit limit required')
    return [
        {'key':(str(r.source_account_ref),str(r.store_id),str(r.item_id)),
         'registry_id':r.id}
        for r in records
    ]


def _candidate_scores(
    source: Session, target: Session, keys: list[Key], cutoff: date,
) -> dict[Key,dict[str,Any]]:
    """Reuse existing 14-day evaluation, never create a second scoring formula."""
    from .bulk_read import load_read_snapshot
    from .models import MarketScore
    from .service import NewProductService
    from .testing_profit import load_testing_profit_page
    from .testing_profit_projection import attach_testing_profit_facts
    from .scoring import evaluate

    svc = NewProductService(target, read_session=source)
    config, version = svc._config()
    source_snap = load_read_snapshot(source, keys, cutoff)
    profit = load_testing_profit_page(source, keys, cutoff)
    markets = {
        (str(m.source_account_ref),str(m.store_id),str(m.item_id)):m
        for m in target.scalars(
            select(MarketScore).where(tuple_(
                MarketScore.source_account_ref,MarketScore.store_id,MarketScore.item_id
            ).in_(keys))
        ).all()
    }
    results = {}
    for key in keys:
        try:
            f = svc._facts(*key, market_score=markets.get(key), snapshot=source_snap)
            attach_testing_profit_facts(f, profit.get(key))
            ev = evaluate(f,config,version)
            results[key] = {'facts': f, 'evaluation':ev, 'rule_version':version}
        except (ValueError, ArithmeticError, KeyError, TypeError) as exc:
            # A data-quality exception cannot silently become a publishable zero.
            LOG.warning('pr337_unified_score_unavailable item=%s type=%s',key[2],type(exc).__name__)
            results[key] = {'facts':{},'evaluation':None,'rule_version':version}
    return results


def _is_frozen(target: Session, key: Key, registry_id: Any) -> bool:
    from .models import NewProductTrackingCurrent, TrackingDecision
    current = target.get(NewProductTrackingCurrent,registry_id)
    if current is not None and current.final_result is not None:
        return True
    return target.scalar(select(TrackingDecision.id).where(
        TrackingDecision.source_account_ref==key[0],
        TrackingDecision.store_id==key[1],
        TrackingDecision.item_id==key[2],
        TrackingDecision.decision.in_(['打品成功','打品失败']),
    ).limit(1)) is not None


def _save_one(
    target: Session, key: Key, ads: dict[str,Any], score: dict[str,Any],
    *, cutoff: date,
) -> str:
    """Local result only. Never override an already published grade/score."""
    from .models import NewProductRegistry,NewProductPerformanceCurrent
    r = target.scalar(select(NewProductRegistry).where(
        NewProductRegistry.source_account_ref==key[0],
        NewProductRegistry.store_id==key[1],
        NewProductRegistry.item_id==key[2],
        NewProductRegistry.is_currently_tagged.is_(True),
    ).limit(1))
    if r is None:
        return 'missing_local_registry'
    if _is_frozen(target,key,r.id):
        return 'frozen'
    p = target.scalar(select(NewProductPerformanceCurrent).where(
        NewProductPerformanceCurrent.registry_id==r.id,
    ).with_for_update())
    if p is not None and p.process_status in {'打品成功','打品失败','成功','失败'}:
        return 'frozen'
    if p is None:
        p = NewProductPerformanceCurrent(registry_id=r.id)
        target.add(p)
    old = p.data_coverage_json if isinstance(p.data_coverage_json,dict) else {}
    updated = dict(old)
    prior = old.get('ad_display_v1')
    # Do not replace a complete, verified snapshot with unavailable evidence.
    # A newer complete result still replaces the old one normally.
    old_complete = isinstance(prior,dict) and prior.get('status') == 'complete'
    new_complete = ads.get('status') == 'complete'
    if not old_complete or new_complete:
        updated['ad_display_v1'] = ads
    evaluation = score.get('evaluation')
    if isinstance(evaluation,dict) and isinstance(evaluation.get('dimensions'),dict):
        # Always reuse evaluate(); preserve existing proofs unless created by
        # this publisher. Do not overwrite historic scores of unknown origin.
        existing = old.get('auto_dimension_scores')
        if existing is None or (isinstance(existing,dict) and existing.get('source')=='unified_publisher_v1'):
            updated['auto_dimension_scores'] = {
                'source':'unified_publisher_v1',
                'rule_version':score['rule_version'],
                'dimensions':evaluation['dimensions'],
                'missing':evaluation.get('missing',[]),
                'calculated_cutoff_la':cutoff.isoformat(),
            }
    if updated==old:
        return 'unchanged'
    p.data_coverage_json = updated
    p.updated_at = datetime.now(UTC)
    # A fresh authoritative grade may be stored only if the current row has
    # never published a grade AND the old dimension evidence is absent or ours.
    # Never overwrite historical grades, frozen results or scoring provenance.
    old_auto = old.get('auto_dimension_scores')
    if (
        p.score is None and p.grade is None
        and isinstance(evaluation, dict)
        and evaluation.get('grade') in {'S','A','B','C','D','Pass'}
        and isinstance(updated.get('auto_dimension_scores'),dict)
        and updated['auto_dimension_scores'].get('source') == 'unified_publisher_v1'
        and (old_auto is None or (
            isinstance(old_auto,dict) and old_auto.get('source')=='unified_publisher_v1'))
    ):
        total = evaluation.get('total')
        try:
            value = Decimal(str(total))
        except (ValueError,TypeError):
            value = None
        if value is not None and value.is_finite() and 0 <= value <= 10:
            p.score=value
            p.grade=evaluation['grade']
            p.calculated_at=datetime.now(UTC)
            facts=score.get('facts') or {}
            if p.first_wfs_available_date_la is None and isinstance(
                facts.get('first_wfs_available_date_la'),date):
                p.first_wfs_available_date_la=facts['first_wfs_available_date_la']
            if p.metric_window_start_la is None and isinstance(
                facts.get('first_wfs_available_date_la'),date):
                p.metric_window_start_la=facts['first_wfs_available_date_la']
            if p.metric_window_end_la is None and isinstance(
                facts.get('observation_end_la'),date):
                p.metric_window_end_la=min(facts['observation_end_la'],cutoff)
            if p.data_status is None:
                p.data_status=str(facts.get('data_status') or 'partial')
    # Never rewrite pre-existing 14-day amounts, score, grade or source history.
    return 'written'


def publish_unified(
    source: Session, target: Session, *,
    item_ids: set[str] | None = None, limit: int = 500,
    cutoff: date | None = None, apply: bool = False,
) -> dict[str,Any]:
    """One publication plan; used by rule apply, daily tick and local CLI alike.

    Fail-closed if requested results are non-local or explicit permission missing.
    The operations/source session must be read-only; caller opens it accordingly.
    """
    if apply and not permission_to_write():
        raise PermissionError('PR337_UNIFIED_PUBLISH_NOT_AUTHORIZED')
    cutoff = cutoff or (datetime.now(LA).date()-timedelta(days=1))
    product_rows = _eligible_rows(source,item_ids,limit)
    keys = [r['key'] for r in product_rows]
    summary: dict[str,Any] = {'dry_run':not apply,'cutoff_la':cutoff.isoformat(),
                               'products':len(keys),'written':0,'frozen':0,
                               'missing_local_registry':0,
                               'incomplete_ads':0,'unverified':0,
                               'samples':[]}
    if not keys:
        return summary
    if not apply:
        from .models import NewProductRegistry
        r = NewProductRegistry
        present = {
            (str(x.source_account_ref),str(x.store_id),str(x.item_id))
            for x in target.scalars(select(r).where(tuple_(
                r.source_account_ref,r.store_id,r.item_id
            ).in_(keys))).all()
        }
        summary['missing_local_registry'] = sum(key not in present for key in keys)
    catalog = load_campaign_catalog(source,cutoff)
    for at in range(0,len(keys),BATCH):
        batch=keys[at:at+BATCH]
        score_map = _candidate_scores(source,target,batch,cutoff)
        # WFS start date comes from authoritative locked WFS evidence, not from
        # an assumed listing created timestamp.
        first_dates = {key:score_map[key]['facts'].get('first_wfs_available_date_la') for key in batch}
        snapshots = load_ad_snapshots(source,batch,first_dates,cutoff,campaign_catalog=catalog)
        for key in batch:
            proof = snapshots[key]
            if proof['status']!='complete':
                summary['incomplete_ads'] += 1
            if score_map[key]['evaluation'] is None:
                summary['unverified'] += 1
            if not apply and len(keys) <= 4:
                displayed = proof.get('facts') or {}
                summary['samples'].append({
                    'item_id':key[2], 'ad_status':proof['status'],
                    'ad_total_spend_usd':displayed.get('ad_total_spend_usd'),
                    'auto_ad_spend_usd':displayed.get('auto_ad_spend_usd'),
                    'manual_ad_spend_usd':displayed.get('manual_ad_spend_usd'),
                    'score_grade':(score_map[key]['evaluation'] or {}).get('grade'),
                })
            if apply:
                outcome=_save_one(target,key,proof,score_map[key],cutoff=cutoff)
                summary[outcome]=summary.get(outcome,0)+1
        if apply:
            # Commit each bounded batch only after its full computation succeeds;
            # one bad batch never silently publishes half of that batch.
            target.commit()
    return summary


def execute_unified_job(*, item_ids: set[str] | None = None,
                        limit: int = 500, apply: bool = False) -> dict[str,Any]:
    """Open existing source/read and decision/write sessions, no new database."""
    from app.db.session import get_engine
    from .read_source import get_new_product_read_session
    if os.getenv('APP_ENV','').strip().lower() not in {'local','dev','development','production'}:
        raise RuntimeError('PR337_APP_ENV_REQUIRED: source/write identity cannot be verified')
    engine = get_engine()
    if apply and os.getenv('APP_ENV','').strip().lower() in {'local','dev','development'}:
        if not local_target_approved(engine.url.database, engine.url.host):
            raise PermissionError('PR337_WRITE_TARGET_NOT_LOCAL_DEV_OR_HYBRID')
    gen = get_new_product_read_session()
    source = next(gen)
    try:
        with Session(engine,autoflush=False,expire_on_commit=False) as target:
            try:
                return publish_unified(source,target,item_ids=item_ids,limit=limit,apply=apply)
            except Exception:
                target.rollback()
                raise
    finally:
        gen.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='Unified new-product performance publication')
    parser.add_argument('--apply',action='store_true',help='Local write only with explicit feature flag')
    parser.add_argument('--limit',type=int,default=500)
    parser.add_argument('--item-ids',default='',help='Comma-separated Walmart Item IDs')
    args = parser.parse_args()
    item_ids = set(args.item_ids.split(',')) if args.item_ids else None
    if item_ids and any(not x or not x.isdigit() for x in item_ids):
        parser.error('Item IDs must be nonempty digits')
    import json
    print(json.dumps(execute_unified_job(item_ids=item_ids,limit=args.limit,apply=args.apply),
                     ensure_ascii=False,sort_keys=True))


if __name__=='__main__':
    main()
