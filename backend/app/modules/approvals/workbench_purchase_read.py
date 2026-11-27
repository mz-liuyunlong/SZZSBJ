"""Authorized page-bounded purchase details; reuse saved evidence and profit engine."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from time import perf_counter
from types import SimpleNamespace
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, text, tuple_

from app.core.api import ApiError
from app.core.permissions import has_permission
from app.modules.approvals.purchase_reference_evidence import purchase_reference_evidence
from app.modules.fx_rates.reader import load_usd_cny_rates, month_key, usd_cny_rate_for
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.new_products.evaluation_workflow import decorate_page
from app.modules.new_products.historical_tracking import snapshots as historical_snapshots
from app.modules.new_products.models import MarketScore, PurchaseApplication, RuleVersion
from app.modules.new_products.persisted_read import load_persisted, snapshot_row
from app.modules.new_products.pr337_daily_view import saved_daily_view
from app.modules.new_products.read_source import get_new_product_read_session
from app.modules.new_products.schemas import ListingQuery
from app.modules.new_products.service import NewProductService, ident, serialized
from app.modules.new_products.testing_profit import (
    _ADS_SQL,
    _DAILY_SQL,
    build_operating_daily_same_source,
    decimal_value,
)
from app.modules.new_products.testing_profit_projection import closed_list_row
from app.modules.product_management.field_access import PURCHASE_COST_PERMISSION
from app.modules.product_management.schemas import ProductManagementListQuery
from app.modules.product_management.service import ProductManagementService
from app.modules.products.dependencies import get_product_scope_provider, require_product_scope

LA = ZoneInfo("America/Los_Angeles")
SH = ZoneInfo("Asia/Shanghai")


def _bad(code):
    raise ApiError(code=code, status_code=409, message="审批数据已变化，请刷新后重试")


def _key(row):
    return tuple(row[k] for k in ("source_account_ref", "store_id", "item_id"))


def _page_sql(statement):
    """Reuse the exact profit SQL with a separate cutoff for each wanted key."""
    sql = statement.text
    if (
        sql.count("SELECT account,store,item FROM jsonb_to_recordset") != 1
        or sql.count("AS j(account text,store text,item text)") != 1
        or sql.count(":cutoff") != 1
    ):
        raise RuntimeError("PURCHASE_PROFIT_SOURCE_CONTRACT_CHANGED")
    return text(
        sql.replace(
            "SELECT account,store,item FROM jsonb_to_recordset",
            "SELECT account,store,item,cutoff FROM jsonb_to_recordset",
        )
        .replace(
            "AS j(account text,store text,item text)",
            "AS j(account text,store text,item text,cutoff date)",
        )
        .replace(":cutoff", "w.cutoff")
    )


_SP_BY_DAY_PAGE = text(
    "\n"
    "WITH wanted AS (\n"
    " SELECT account,store,item,cutoff FROM jsonb_to_recordset(CAST(:wanted AS "
    "jsonb))\n"
    " AS j(account text,store text,item text,cutoff date)\n"
    ")\n"
    "SELECT w.account,w.store,w.item,a.business_date_la AS day,\n"
    " COUNT(a.id) AS source_rows,\n"
    " COUNT(a.id) FILTER (WHERE a.ad_spend_amount IS NULL OR a.ad_spend_currency_code "
    "IS DISTINCT FROM 'USD') AS incomplete_spend_rows,\n"
    " SUM(a.ad_spend_amount) FILTER (WHERE a.ad_spend_currency_code='USD') AS "
    "sp_spend\n"
    "FROM wanted w JOIN fact_walmart_ad_item_sp_daily a\n"
    " ON a.source_account_ref=w.account AND a.store_id=w.store AND a.item_id=w.item\n"
    " AND a.business_date_la<=w.cutoff\n"
    "GROUP BY w.account,w.store,w.item,a.business_date_la\n"
    "ORDER BY w.account,w.store,w.item,a.business_date_la\n"
)


def _batch_profit_daily(source, contexts):
    if not contexts:
        return {}
    if len(contexts) > 200:
        raise ValueError("PURCHASE_PAGE_TOO_LARGE")
    wants = json.dumps(
        [
            dict(account=k[0], store=k[1], item=k[2], cutoff=c["cutoff"].isoformat())
            for k, c in contexts.items()
        ]
    )
    groups = defaultdict(list)
    ads = defaultdict(list)
    totals = {}
    for row in source.execute(_page_sql(_DAILY_SQL), {"wanted": wants}).mappings():
        groups[(row["account"], row["store"], row["item"])].append(dict(row))
    for row in source.execute(_page_sql(_ADS_SQL), {"wanted": wants}).mappings():
        totals[(row["account"], row["store"], row["item"])] = dict(row)
    for row in source.execute(_SP_BY_DAY_PAGE, {"wanted": wants}).mappings():
        ads[(row["account"], row["store"], row["item"])].append(dict(row))
    return {
        k: build_operating_daily_same_source(groups[k], totals.get(k), ads[k], **c)
        for k, c in contexts.items()
    }


def _batch_score_rows(service, accounts, keys):
    """Batch equivalent of persisted_score's exact identity and saved-view path."""
    if not keys:
        return {}
    historical = historical_snapshots(service.db, accounts, keys)
    page, total, _ = service.repo.page(
        accounts, page=1, page_size=len(keys), item_keys=keys, historical_keys=historical
    )
    if total != len(page.items):
        _bad("WORKBENCH_LISTING_AMBIGUOUS")
    listings = {ident(r): r for r in page.items}
    if len(listings) != len(page.items):
        _bad("WORKBENCH_LISTING_AMBIGUOUS")
    if not listings:
        return {}
    matched = load_persisted(service.repo.session, listings)
    first = service.repo.first_order_dates(page.items)
    markets = {
        ident(m): m
        for m in service.db.scalars(
            select(MarketScore).where(
                tuple_(
                    MarketScore.source_account_ref, MarketScore.store_id, MarketScore.item_id
                ).in_(listings)
            )
        ).all()
    }
    finals = service._final_decisions(list(historical)) if historical else {}
    today = datetime.now(LA).date()
    result = {}
    for key, listing in listings.items():
        row = snapshot_row(listing, first.get(key), matched.get(key), markets.get(key), today)
        saved_daily_view(row, matched.get(key))
        if key in historical and key in finals:
            row = closed_list_row(
                listing.model_dump(mode="json"), matched.get(key), finals[key], today
            )
        result[key] = row
    # Single-item persisted_score uses distinct historical/normal paths.
    for historic in (False, True):
        group = [k for k in result if (k in historical) == historic]
        if group:
            service._hydrate_workflow_rows(
                [result[k] for k in group],
                {k: matched[k] for k in group if k in matched},
                historical={k: historical[k] for k in group} if historic else {},
            )
    return result


def _parse_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _daily_for_scores(session, source, scores):
    saved = load_persisted(session, scores)
    today_cutoff = datetime.now(LA).date() - timedelta(days=1)
    result, contexts, overviews = {}, {}, {}
    for key, score in scores.items():
        evidence = score.get("facts") or {}
        evaluation = score.get("evaluation") or {}
        first = _parse_date(
            evidence.get("first_wfs_available_date_la")
            or score["listing"].get("first_wfs_available_date_la")
        )
        frozen = evaluation.get("grade") is not None and evaluation.get("total") is not None
        matched = saved.get(key)
        perf = matched[1] if matched else None
        coverage = perf.data_coverage_json if perf else {}
        archive = (coverage or {}).get("evaluation_operating_archive_v1")
        archive = archive if isinstance(archive, dict) else {}
        overviews[key] = archive.get("overview")
        if frozen and isinstance(archive.get("daily"), dict):
            result[key] = dict(archive["daily"])
            continue
        cutoff = today_cutoff
        reason = None
        if frozen:
            original = _parse_date(evidence.get("data_cutoff_la"))
            if original is not None:
                if original > cutoff:
                    reason = "frozen_profit_cutoff_in_future"
                else:
                    cutoff = original
        if first is None:
            reason = "first_wfs_date_unverified"
        if reason:
            result[key] = {
                "status": "unverified",
                "reason": reason,
                "rows": [],
                "totals": None,
                "cutoff_la": cutoff.isoformat(),
                "source": "new_products_testing_profit_full_history_v2",
            }
        else:
            contexts[key] = {"cutoff": cutoff, "first_wfs": first, "saved_facts": evidence}
    result.update(_batch_profit_daily(source, contexts))
    return {k: {**daily, "frozen_overview": overviews[k]} for k, daily in result.items()}


def _batch_evidence(session, applications):
    if not applications:
        return {}
    versions = {
        r.version: r
        for r in session.scalars(
            select(RuleVersion).where(
                RuleVersion.kind == "performance",
                RuleVersion.version.in_({a.score_rule_version for a in applications}),
            )
        ).all()
    }
    events = defaultdict(list)
    # Preserve the original as-of cutoff and 120-event limit per application.
    sql = text("""SELECT a.id::text AS application_id,e.event_type,e.payload_json
      FROM biz_new_product_purchase_applications a
      JOIN LATERAL (SELECT event_type,payload_json,created_at,id FROM biz_new_product_action_events
       WHERE source_account_ref=a.source_account_ref AND store_id=a.store_id AND item_id=a.item_id
        AND created_at<=a.created_at ORDER BY created_at DESC,id DESC LIMIT 120) e ON TRUE
      WHERE a.id::text=ANY(:ids)
      ORDER BY a.id,e.created_at DESC,e.id DESC""")
    for r in session.execute(sql, {"ids": [str(a.id) for a in applications]}).mappings():
        events[r["application_id"]].append(
            SimpleNamespace(event_type=r["event_type"], payload_json=r["payload_json"])
        )
    return {
        str(a.id): purchase_reference_evidence(
            session, a, preloaded=(versions.get(a.score_rule_version), events[str(a.id)])
        )
        for a in applications
    }


def _catalog(session, principal, accounts, keys):
    if not keys or not has_permission(principal, "products:read"):
        return {}
    try:
        require_product_scope(principal, get_product_scope_provider())
    except ApiError:
        return {}
    can_cost = has_permission(principal, "products:cost:read") or has_permission(
        principal, PURCHASE_COST_PERMISSION
    )
    skus = sorted({sku for _, sku in keys})
    found = defaultdict(list)
    svc = ProductManagementService(session)
    for start in range(0, len(skus), 25):
        batch = skus[start : start + 25]
        data, total, _, _ = svc.list_skus(
            ProductManagementListQuery(page=1, page_size=100, sku_batch=batch),
            accounts,
            include_costs=can_cost,
        )
        if total != len(data.items):
            continue
        for row in data.items:
            key = (row.source_account_ref, row.sku)
            if key in keys:
                found[key].append((row.owner_name, row.purchase_cost_cny if can_cost else None))
    return {k: rows[0] for k, rows in found.items() if len(rows) == 1}


def enrich_purchase_page(session, principal, accounts, provider, items, *, timings=None):
    """Attach display data only to authorized, same-version current-page rows."""
    timings = {} if timings is None else timings
    stage = perf_counter()
    wanted = [r for r in items if r.approval_type == "new_product_purchase"]
    if not wanted:
        return {}
    if len(wanted) > 200:
        _bad("WORKBENCH_PAGE_TOO_LARGE")
    apps = {
        str(a.id): a
        for a in session.scalars(
            select(PurchaseApplication).where(
                PurchaseApplication.id.in_([UUID(r.id) for r in wanted]),
                PurchaseApplication.source_account_ref.in_(accounts),
            )
        ).all()
    }
    for row in wanted:
        app = apps.get(row.id)
        if (
            not app
            or app.version != row.version
            or app.status != row.status
            or app.applicant_id != row.applicant_id
            or ident(app)
            != (
                row.source_account_ref,
                row.purchase_details.get("store_id"),
                row.purchase_details.get("item_id"),
            )
        ):
            _bad("WORKBENCH_APPLICATION_CHANGED")
    evidence = _batch_evidence(session, list(apps.values()))
    fx = load_usd_cny_rates(session)
    timings["purchase_evidence_fx"] = (perf_counter() - stage) * 1000
    stage = perf_counter()
    # Preserve the existing dedicated operational read session and IAM scope.
    reader = get_new_product_read_session()
    source = next(reader)
    try:
        try:
            allowed = accounts.intersection(
                require_source_account_scope(principal, provider, source)
            )
        except ApiError as exc:
            if exc.status_code != 403:
                raise
            allowed = frozenset()
        keys = sorted({ident(a) for a in apps.values() if a.source_account_ref in allowed})
        svc = NewProductService(session, read_session=source)
        timings["purchase_source_scope"] = (perf_counter() - stage) * 1000
        stage = perf_counter()
        if keys:
            data = decorate_page(
                session,
                svc.list(allowed, ListingQuery(page=1, page_size=len(keys)), scope_keys=keys),
            )
            listing_rows = defaultdict(list)
            for entry in data["items"]:
                listing_rows[_key(entry["listing"])].append(entry)
            listings = {k: r[0] for k, r in listing_rows.items() if len(r) == 1 and k in keys}
            if data["total"] != len(data["items"]):
                _bad("WORKBENCH_LISTING_AMBIGUOUS")
            timings["purchase_listing"] = (perf_counter() - stage) * 1000
            stage = perf_counter()
            score_rows = _batch_score_rows(svc, allowed, keys)
            timings["purchase_score_rows"] = (perf_counter() - stage) * 1000
            stage = perf_counter()
            daily = _daily_for_scores(session, source, score_rows)
            timings["purchase_daily"] = (perf_counter() - stage) * 1000
        else:
            listings, daily = {}, {}
    finally:
        reader.close()
    catalog_keys = set()
    for app in apps.values():
        entry = listings.get(ident(app))
        sku = (entry["listing"].get("local_sku") or "").strip() if entry else ""
        if sku and sku not in {"-", "—"}:
            catalog_keys.add((app.source_account_ref, sku))
    stage = perf_counter()
    catalog = _catalog(session, principal, accounts, catalog_keys)
    timings["purchase_catalog"] = (perf_counter() - stage) * 1000
    stage = perf_counter()
    result = {}
    for row in wanted:
        app = apps[row.id]
        details = row.purchase_details
        day = app.created_at.astimezone(SH).date()
        rate = usd_cny_rate_for(fx, day)
        details.update(
            approval_evidence=evidence[row.id],
            profit_fx_month=month_key(day),
            profit_fx_rate=str(rate) if rate is not None else None,
            profit_fx_source="lingxing_my_rate",
        )
        entry = listings.get(ident(app))
        sku = (entry["listing"].get("local_sku") or "").strip() if entry else ""
        snap = (details.get("sku") or "").strip()
        owner, cost = (
            catalog.get((app.source_account_ref, sku), (None, None))
            if sku and (not snap or snap in {"-", "—"} or sku == snap)
            else (None, None)
        )
        if owner and (
            not details.get("owner_name")
            or details["owner_name"] in {"—", "未分配", "负责人待确认"}
        ):
            details["owner_name"] = owner
        amount = decimal_value(cost)
        if amount is not None and amount >= 0:
            details["amount"] = str(amount * app.requested_qty)
            details["currency_code"] = "CNY"
        result[row.id] = {
            "application_id": row.id,
            "version": row.version,
            "source_account_ref": row.source_account_ref,
            "store_id": app.store_id,
            "item_id": app.item_id,
            "listing": serialized(entry) if entry else None,
            "daily": serialized(daily.get(ident(app))),
            "unit_purchase_cost_cny": str(amount) if amount is not None and amount >= 0 else None,
        }
    timings["purchase_result"] = (perf_counter() - stage) * 1000
    return result
