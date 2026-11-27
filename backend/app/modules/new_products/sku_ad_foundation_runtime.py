"""0100 independent source projections; never mutate the legacy data layer."""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations.lingxing.security import canonical_json, redact_json

from . import sku_ad_foundation_models as m
from . import sku_ad_foundation_projection as p

logger = logging.getLogger(__name__)
LA = ZoneInfo("America/Los_Angeles")
FRESHNESS = timedelta(hours=48)
RULE = "observed-enabled-config-v1"


def _normal(value):
    return " ".join(str(value or "").strip().casefold().split())


def _signature(row):
    return canonical_json(redact_json(dict(row)))


def _ready(session, table):
    return (
        session.execute(sa.text("select to_regclass(:name)"), {"name": table.name}).scalar()
        is not None
    )


def _upsert(session, table, values, *, newer=None):
    stmt = insert(table).values(**values)
    keys = [c.name for c in table.primary_key]
    changes = {key: stmt.excluded[key] for key in values if key not in keys}
    if "updated_at" in table.c:
        changes["updated_at"] = sa.func.now()
    kw = (
        {}
        if newer is None
        else {"where": sa.or_(table.c[newer].is_(None), stmt.excluded[newer] >= table.c[newer])}
    )
    session.execute(stmt.on_conflict_do_update(index_elements=keys, set_=changes, **kw))


def collect_ad_page(runner, parser_key, blob_id, response):
    """Capture exact page provenance in memory; never performs SQL or network I/O."""
    if parser_key not in ("walmart_ad_item_sp_list", "walmart_advertiser_list") or blob_id is None:
        return
    try:
        rows = p.ad_payload_rows(response.response_json)
        seen = response.pulled_at
        p.require_observed_at(seen)
        page = (parser_key, UUID(str(blob_id)), seen, rows)
        if not hasattr(runner, "_foundation_ad_pages"):
            runner._foundation_ad_pages = []
        runner._foundation_ad_pages.append(page)
    except Exception as exc:
        # No response bodies or secrets in logs. Original writer remains authoritative.
        runner._foundation_ad_capture_failed = True
        logger.warning("foundation_ad_capture_skipped error_type=%s", type(exc).__name__)


def save_ad_source_page(session, *, account, day, kind, blob, seen, rows):
    """Keep every row, including incomplete IDs and dedup losers. No inferred date."""
    table = m.WalmartAdSourceObservation_table
    for ordinal, row in enumerate(rows):
        key = hashlib.sha256(
            canonical_json(
                [account, day.isoformat() if day else None, kind, str(blob), ordinal]
            ).encode("utf-8")
        ).hexdigest()
        values = dict(
            observation_key=key,
            source_account_ref=account,
            source_interface=kind,
            business_date_la=day,
            source_blob_id=blob,
            source_ordinal=ordinal,
            first_observed_at=seen,
            last_observed_at=seen,
            payload_json=p.safe_payload(row),
        )
        stmt = insert(table).values(**values)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["observation_key"],
                set_={
                    "first_observed_at": sa.func.least(
                        table.c.first_observed_at, stmt.excluded.first_observed_at
                    ),
                    "last_observed_at": sa.func.greatest(
                        table.c.last_observed_at, stmt.excluded.last_observed_at
                    ),
                },
            )
        )


def _ad_lineage(pages):
    result = {}
    for kind, blob, seen, rows in pages:
        if kind != "walmart_ad_item_sp_list":
            continue
        for ordinal, row in enumerate(rows):
            key = _signature(row)
            old = result.get(key)
            if old is None or seen > old[2]:
                result[key] = (blob, ordinal, seen, row)
    return result


def confirmed_store(*, store_names, item_stores, facts, explicit_store=None):
    """Require independent evidence; never infer from substring or Item ID alone."""
    candidates = set()
    conflict = False
    for seller, item, fact_store in facts:
        if not seller:
            continue
        matches = store_names.get(_normal(seller), set())
        if len(matches) != 1:
            conflict = True
            continue
        sid = next(iter(matches))
        if sid not in item_stores.get(item, set()) or fact_store != sid:
            conflict = True
            continue
        candidates.add(sid)
    if explicit_store:
        candidates.add(explicit_store)
    if conflict or len(candidates) > 1:
        return None, "ambiguous"
    if not candidates:
        return None, "unmapped"
    return next(iter(candidates)), "confirmed"


def observed_enabled(row, account_status, seen, now):
    """Positive observation of configured enabled, not proof of delivery or full coverage."""
    if not now - FRESHNESS <= seen <= now:
        return False
    return (
        _normal(account_status) == "1"
        and _normal(row.get("campaignStatus")) in {"enabled", "live"}
        and _normal(row.get("adGroupStatus")) == "enabled"
        and _normal(row.get("adStatus")) == "enabled"
        and _normal(row.get("reviewStatus")) == "approved"
    )


def current_report_day(day, now):
    today = now.astimezone(LA).date()
    return today - timedelta(days=1) <= day <= today


def _write_ad_day(session, *, account, day, pages, selected, complete, now, committed_at=None):
    """Write only extension tables. Date/hash come from the actual legacy writer."""
    configs = m.WalmartAdItemConfigExtension_table
    daily = m.WalmartAdItemDailyExtension_table
    mapping = m.WalmartAdAccountStoreMapping_table
    statuses = m.ListingAdStatusCurrent_table
    lineage = _ad_lineage(pages)
    if not complete or not any(kind == "walmart_advertiser_list" for kind, *_ in pages):
        raise ValueError("FOUNDATION_CAPTURE_INCOMPLETE")
    if selected and not lineage:
        raise ValueError("FOUNDATION_AD_LINEAGE_MISSING")
    facts = {
        (row["advertiser_id"], row["source_line_hash"]): row
        for row in session.execute(
            sa.text(
                "\n"
                "        select advertiser_id, source_line_hash, store_id, item_id, "
                "campaign_id, ad_group_id, ad_item_id,\n"
                "          ad_spend_currency_code, synced_at from "
                "fact_walmart_ad_item_sp_daily\n"
                "        where source_account_ref=:account and business_date_la=:day\n"
                "        "
            ),
            {"account": account, "day": day},
        ).mappings()
    }
    if set(facts) != set(selected):
        raise ValueError("FOUNDATION_FACT_SET_CHANGED")
    advertisers = {
        row["advertiser_id"]: row
        for row in session.execute(
            sa.text(
                "\n"
                "        select advertiser_id, advertiser_name, raw_status, store_id, "
                "synced_at from dim_walmart_advertisers\n"
                "        where source_account_ref=:account\n"
                "        "
            ),
            {"account": account},
        ).mappings()
    }
    # Ensure the exact selected legacy row is present in the actual source page, not a guessed join.
    observations = []
    for key, row in selected.items():
        raw = lineage.get(_signature(row))
        if raw is None:
            raise ValueError("FOUNDATION_AD_SELECTED_ROW_UNVERIFIED")
        blob, ordinal, seen, original = raw
        fact = facts[key]
        if fact["synced_at"] < seen or fact["synced_at"] > (committed_at or now):
            raise ValueError("FOUNDATION_FACT_OBSERVATION_CHANGED")
        try:
            config, metrics = p.project_ad(original)
        except ValueError as exc:
            if str(exc) == "FOUNDATION_AD_IDENTITY_INCOMPLETE":
                logger.warning("foundation_ad_incomplete_identity")
                continue
            raise
        if any(
            fact[k] != config[k] for k in ("item_id", "campaign_id", "ad_group_id", "ad_item_id")
        ):
            raise ValueError("FOUNDATION_AD_FACT_IDENTITY_CHANGED")
        if config["advertiser_id"] != key[0] or key[0] not in advertisers:
            raise ValueError("FOUNDATION_AD_ACCOUNT_UNVERIFIED")
        observations.append((key, original, blob, ordinal, seen, config, metrics, fact))
    # Account/date replacement in the new table only. Preserve existing values on any failure.
    session.execute(
        daily.delete().where(daily.c.source_account_ref == account, daily.c.business_date_la == day)
    )
    for key, _original, blob, ordinal, seen, _config, metrics, fact in observations:
        _upsert(
            session,
            daily,
            dict(
                metrics,
                source_account_ref=account,
                business_date_la=day,
                source_line_hash=key[1],
                source_blob_id=blob,
                source_ordinal=ordinal,
                source_observed_at=seen,
                currency_code=fact["ad_spend_currency_code"],
            ),
        )
    # Include every source row with a complete identity, even those deduplicated from the legacy
    # fact.
    for blob, ordinal, seen, row in lineage.values():
        try:
            config, _ = p.project_ad(row)
        except ValueError as exc:
            if str(exc) == "FOUNDATION_AD_IDENTITY_INCOMPLETE":
                continue
            raise
        if config["advertiser_id"] not in advertisers:
            continue
        _upsert(
            session,
            configs,
            dict(
                config,
                source_account_ref=account,
                source_blob_id=blob,
                source_ordinal=ordinal,
                source_observed_at=seen,
            ),
            newer="source_observed_at",
        )
    if not current_report_day(day, now):
        return {"daily": len(observations), "status": "historical_day_not_published"}
    store_names = defaultdict(set)
    store_ids = set()
    for sid, name in session.execute(
        sa.text(
            "select store_id,store_name from dim_lingxing_stores\n"
            "        where source_account_ref=:account and (platform_code_raw='10008' "
            "or lower(platform_code)='walmart' or platform_code='10008') "
        ),
        {"account": account},
    ):
        store_ids.add(sid)
        if name:
            store_names[_normal(name)].add(sid)
    item_stores = defaultdict(set)
    for sid, iid in session.execute(
        sa.text("""select store_id,item_id from dim_walmart_listings
        where source_account_ref=:account"""),
        {"account": account},
    ):
        item_stores[iid].add(sid)
    ad_pages = {}
    for kind, blob, seen, rows in pages:
        if kind == "walmart_advertiser_list":
            for row in rows:
                aid = p.source_text(row.get("advertiserId"), 128)
                if aid and (aid not in ad_pages or seen > ad_pages[aid][1]):
                    ad_pages[aid] = (blob, seen, row)
    grouped = defaultdict(list)
    for obs in observations:
        grouped[obs[0][0]].append(obs)
    resolved = {}
    for aid, (blob, seen, raw) in ad_pages.items():
        if aid not in advertisers:
            continue
        explicit = p.source_text(raw.get("storeId") or raw.get("store_id"), 128)
        if explicit not in store_ids:
            explicit = None
        evidence = [
            (x[1].get("mpSellerName"), x[5]["item_id"], x[7]["store_id"]) for x in grouped[aid]
        ]
        sid, state = confirmed_store(
            store_names=store_names,
            item_stores=item_stores,
            facts=evidence,
            explicit_store=explicit,
        )
        raw_status = p.source_text(raw.get("status"), 128)
        resolved[aid] = (sid, state, raw_status, seen)
        sellers = sorted({str(x[0]) for x in evidence if x[0]})
        _upsert(
            session,
            mapping,
            dict(
                source_account_ref=account,
                advertiser_id=aid,
                store_id=sid,
                mapping_status=state,
                source_advertiser_name=p.source_text(raw.get("advertiserName")),
                source_status_raw=raw_status,
                source_seller_name=sellers[0] if len(sellers) == 1 else None,
                source_blob_id=blob,
                source_observed_at=seen,
                confirmed_by="system" if sid else None,
                confirmed_at=now if sid else None,
                evidence_json={
                    "method": "exact_seller_name_and_listing_fact_or_explicit_store",
                    "sellers": sellers,
                    "business_date_la": day.isoformat(),
                    "advertiser_payload": p.safe_payload(raw),
                },
            ),
            newer="source_observed_at",
        )
    # Never publish false based on absence. Older report days must not override newer evidence.
    day_text = day.isoformat()
    previous_day = statuses.c.evidence_json["business_date_la"].astext
    session.execute(
        statuses.update()
        .where(
            statuses.c.source_account_ref == account,
            sa.or_(previous_day.is_(None), previous_day <= day_text),
        )
        .values(
            ad_enabled=None,
            ad_status_checked_at=now,
            unknown_reason="no_current_positive_evidence",
            rule_version=RULE,
            evidence_json={"business_date_la": day_text},
            updated_at=sa.func.now(),
        )
    )
    enabled = {}
    conflicting = set()
    states = defaultdict(set)
    for _blob, _ordinal, _seen, raw in lineage.values():
        identity = tuple(
            p.source_text(raw.get(k), 128)
            for k in ("advertiserId", "campaignId", "adGroupId", "adItemId", "itemId")
        )
        states[identity].add(
            tuple(
                _normal(raw.get(k))
                for k in ("campaignStatus", "adGroupStatus", "adStatus", "reviewStatus")
            )
        )
    conflicting = {identity for identity, states_for_id in states.items() if len(states_for_id) > 1}
    for key, row, blob, ordinal, seen, config, _metrics, fact in observations:
        sid, state, raw_status, account_seen = resolved.get(key[0], (None, None, None, None))
        if (
            not sid
            or state != "confirmed"
            or fact["store_id"] != sid
            or sid not in item_stores.get(config["item_id"], set())
        ):
            continue
        identity = tuple(
            config[k]
            for k in ("advertiser_id", "campaign_id", "ad_group_id", "ad_item_id", "item_id")
        )
        if identity in conflicting or not observed_enabled(
            row, raw_status, min(seen, account_seen), now
        ):
            continue
        ident = (sid, config["item_id"])
        old = enabled.get(ident)
        if old is None or seen > old[0]:
            enabled[ident] = (seen, blob, ordinal, key[0])
    for (sid, iid), (seen, blob, ordinal, aid) in enabled.items():
        values = dict(
            source_account_ref=account,
            store_id=sid,
            item_id=iid,
            ad_enabled=True,
            source_observed_at=seen,
            ad_status_checked_at=now,
            rule_version=RULE,
            unknown_reason=None,
            evidence_json={
                "business_date_la": day_text,
                "blob_id": str(blob),
                "ordinal": ordinal,
                "advertiser_id": aid,
                "coverage_verified": False,
                "meaning": "observed_enabled_configuration",
            },
        )
        stmt = insert(statuses).values(**values)
        keys = ["source_account_ref", "store_id", "item_id"]
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=keys,
                set_={
                    **{k: stmt.excluded[k] for k in values if k not in keys},
                    "updated_at": sa.func.now(),
                },
                where=sa.or_(previous_day.is_(None), previous_day <= day_text),
            )
        )
    return {"daily": len(observations), "enabled": len(enabled), "mappings": len(resolved)}


def after_ad_fact_commit(runner, rows):
    """Called after original source commit, before original MART processing. Own transaction."""
    pages = getattr(runner, "_foundation_ad_pages", [])
    if not pages or not isinstance(runner.session, Session):
        return
    session = runner.session
    committed_at = datetime.now(UTC)
    try:
        from app.modules.integration_sync.data_pages_real_sync import (
            _ad_identity_hash,
            _dedupe_ad_rows_for_resolution,
            _field,
        )

        if not _ready(session, m.WalmartAdItemDailyExtension_table):
            session.rollback()
            return
        selected = {
            (_field(row, "advertiserId", "advertiser_id"), _ad_identity_hash(row)): row
            for row in _dedupe_ad_rows_for_resolution(rows)
            if _field(row, "advertiserId", "advertiser_id")
        }
        # Extension-only lock. No locks on existing facts or marts. Failed extension rolls back
        # alone.
        session.execute(sa.text("set local lock_timeout='1000ms'"))
        session.execute(sa.text("set local statement_timeout='30s'"))
        session.execute(
            sa.text("select pg_advisory_xact_lock(hashtextextended(:k,0))"),
            {"k": "foundation-ad:" + runner.source_account_ref},
        )
        for kind, blob, seen, raw_rows in pages:
            save_ad_source_page(
                session,
                account=runner.source_account_ref,
                day=runner.business_date if kind == "walmart_ad_item_sp_list" else None,
                kind=kind,
                blob=blob,
                seen=seen,
                rows=raw_rows,
            )
        session.commit()
        session.execute(sa.text("set local lock_timeout='1000ms'"))
        session.execute(sa.text("set local statement_timeout='30s'"))
        session.execute(
            sa.text("select pg_advisory_xact_lock(hashtextextended(:k,0))"),
            {"k": "foundation-ad:" + runner.source_account_ref},
        )
        result = _write_ad_day(
            session,
            account=runner.source_account_ref,
            day=runner.business_date,
            pages=pages,
            selected=selected,
            complete=not getattr(runner, "_foundation_ad_capture_failed", False),
            now=datetime.now(UTC),
            committed_at=committed_at,
        )
        session.commit()
        logger.info("foundation_ad_projection %s", result)
    except Exception as exc:
        session.rollback()
        logger.warning("foundation_ad_projection_failed error_type=%s", type(exc).__name__)


def sku_refs(
    session, *, run_id=None, account=None, after=None, before=None, cursor=None, limit=200
):
    if not 1 <= limit <= 2000 or (
        run_id is None and (not account or after is None or before is None)
    ):
        raise ValueError("FOUNDATION_REPLAY_SCOPE_REQUIRED")
    conditions = [
        "r.is_success",
        "s.provider='lingxing'",
        "s.status='succeeded'",
        "s.interface_key in ('productList','batchGetProductInfo')",
        "b.storage_mode='database'",
        "b.payload_json is not null",
    ]
    args = {"limit": limit}
    if run_id is not None:
        conditions.append("r.run_id=:run_id")
        args["run_id"] = run_id
    else:
        conditions.extend(
            ["s.source_account_ref=:account", "r.received_at>=:after", "r.received_at<:before"]
        )
        args.update(account=account, after=after, before=before)
    if cursor is not None:
        conditions.append("(r.received_at,r.id)<(:cursor_at,:cursor_id)")
        args.update(cursor_at=cursor[0], cursor_id=cursor[1])
    stmt = sa.text(
        (
            "select r.id,r.received_at from ods_api_raw_request_refs r join "
            "gov_integration_sync_runs s on s.id=r.run_id join ods_api_raw_blobs b on "
            "b.id=r.raw_blob_id where "
        )
        + " and ".join(conditions)
        + " order by r.received_at desc,r.id desc limit :limit"
    )
    return list(session.execute(stmt, args).all())


def replay_sku_refs(session, refs):
    result = {"pages_ok": 0, "pages_failed": 0}
    for ref in reversed(refs):
        try:
            session.execute(sa.text("set local lock_timeout='1000ms'"))
            session.execute(sa.text("set local statement_timeout='30s'"))
            p.publish_sku_raw_page(session, ref)
            session.commit()
            result["pages_ok"] += 1
        except Exception as exc:
            session.rollback()
            result["pages_failed"] += 1
            logger.warning(
                "foundation_sku_page_failed ref=%s error_type=%s", ref, type(exc).__name__
            )
    return result


def after_sku_run(session, run_id):
    """Separate session after governed run completion; failure never changes run status."""
    if not isinstance(session, Session):
        return
    try:
        if not _ready(session, m.LingxingSkuSourceCurrent_table):
            return
        cursor = None
        totals = {"pages_ok": 0, "pages_failed": 0}
        while True:
            refs = sku_refs(session, run_id=run_id, cursor=cursor, limit=200)
            session.rollback()
            if not refs:
                break
            result = replay_sku_refs(session, [r[0] for r in refs])
            for key in totals:
                totals[key] += result[key]
            cursor = (refs[-1][1], refs[-1][0])
            if len(refs) < 200:
                break
        if any(totals.values()):
            logger.info("foundation_sku_projection run_id=%s %s", run_id, totals)
    except Exception as exc:
        session.rollback()
        logger.warning("foundation_sku_projection_failed error_type=%s", type(exc).__name__)


def read_dates(session, keys):
    """Only keys already filtered by the existing account/permission checks."""
    keys = list(set(keys))
    if not keys or not isinstance(session, Session):
        return {}
    current, snapshot = m.LingxingSkuSourceCurrent_table, m.LingxingSkuSourceSnapshot_table
    try:
        with session.begin_nested():
            if not _ready(session, current):
                return {}
            rows = session.execute(
                sa.select(
                    current.c.source_account_ref,
                    current.c.sku_identity_id,
                    snapshot.c.source_created_at,
                )
                .join(snapshot, snapshot.c.id == current.c.snapshot_id)
                .where(
                    current.c.source_interface == "productList",
                    sa.tuple_(current.c.source_account_ref, current.c.sku_identity_id).in_(keys),
                )
            ).all()
            return {(a, i): d for a, i, d in rows}
    except sa.exc.SQLAlchemyError as exc:
        logger.warning("foundation_date_read_unavailable error_type=%s", type(exc).__name__)
        return {}


def read_listing_statuses(session, keys, *, now=None):
    keys = list(set(keys))
    now = now or datetime.now(UTC)
    if not keys or not isinstance(session, Session):
        return {}
    t = m.ListingAdStatusCurrent_table
    try:
        with session.begin_nested():
            if not _ready(session, t):
                return {}
            rows = session.execute(
                sa.select(
                    t.c.source_account_ref,
                    t.c.store_id,
                    t.c.item_id,
                    t.c.ad_enabled,
                    t.c.ad_status_checked_at,
                    t.c.source_observed_at,
                ).where(sa.tuple_(t.c.source_account_ref, t.c.store_id, t.c.item_id).in_(keys))
            ).all()
            return {
                (a, s, i): (v if seen and now - FRESHNESS <= seen <= now else None, checked)
                for a, s, i, v, checked, seen in rows
            }
    except sa.exc.SQLAlchemyError as exc:
        logger.warning("foundation_ad_status_read_unavailable error_type=%s", type(exc).__name__)
        return {}
