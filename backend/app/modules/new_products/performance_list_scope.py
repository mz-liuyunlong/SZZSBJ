"""Read-only, permission-scoped listing projection for New Product performance.

A small, exact-identity projection drives the global cards and server filters.
Operations MART and decision DB can be different read targets (Hybrid safety).
No scoring or mutation takes place during list/summary requests.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, tuple_

from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.data_pages.repository import LISTING_WFS_LA_LOCKED, PRODUCT_INFO_CURRENT
from app.modules.walmart_monitor.models import WalmartMonitorListingCurrent

from .category_zh import business_category, category_path_detail, translate_category
from .evaluation_policy import evaluation_status

SAMPLE_TAG = "小批量测品"
LA = ZoneInfo("America/Los_Angeles")
_STATUSES = ("待到货", "测评中", "待市场评分", "待等级确认", "待测评确认", "测评通过", "测评未通过")
_GRADES = ("S", "A", "B", "C", "D", "Pass")
_LOGGER = logging.getLogger(__name__)


def scoped_projection(source, db, accounts: frozenset[str]) -> list[dict]:
    """One MART read + one decision read + one owner lookup, never N+1."""
    if not accounts:
        return []
    started = time.monotonic()
    m = ListingManagementCurrentMart
    monitor = WalmartMonitorListingCurrent
    stmt = (
        select(
            m.source_account_ref,
            m.store_id,
            m.item_id,
            m.local_sku,
            m.local_name,
            m.title,
            func.coalesce(
                func.nullif(func.btrim(monitor.category), ""),
                func.nullif(func.btrim(m.category), ""),
            ).label("category_raw"),
            m.listing_start_at_utc,
        )
        .where(
            m.source_account_ref.in_(accounts),
            m.product_tags_json.contains([{"label": SAMPLE_TAG}]),
        )
        .outerjoin(
            monitor,
            (monitor.source_account_ref == m.source_account_ref)
            & (monitor.store_id == m.store_id)
            & (monitor.item_id == m.item_id),
        )
    )
    has_locked = (
        source.scalar(text("SELECT to_regclass('public.listing_wfs_first_stock_la_locked')"))
        is not None
    )
    if has_locked:
        locked = LISTING_WFS_LA_LOCKED
        stmt = stmt.add_columns(locked.c.first_wfs_available_date_la.label("source_first_wfs"))
        stmt = stmt.outerjoin(
            locked,
            (locked.c.source_account_ref == m.source_account_ref)
            & (locked.c.store_id == m.store_id)
            & (locked.c.item_id == m.item_id),
        )
    rows = source.execute(stmt).mappings().all()
    mart_ms = int((time.monotonic() - started) * 1000)
    if len(rows) > 5000:
        raise ValueError("NEW_PRODUCT_SUMMARY_OVER_5000")
    if not rows:
        return []

    keys = [(str(r["source_account_ref"]), str(r["store_id"]), str(r["item_id"])) for r in rows]
    # Decision rows are read on the actual application DB, never through
    # an unsafe cross-database JOIN or a source write credential.
    decision = (
        db.execute(
            text("""
        WITH wanted AS (
          SELECT a,s,i FROM jsonb_to_recordset(CAST(:wants AS jsonb))
          AS w(a text,s text,i text)
        )
        SELECT w.a,w.s,w.i,r.listing_date_la,
          p.first_wfs_available_date_la, p.score,p.grade,
          p.data_coverage_json -> 'operator_assessment_v1' AS operator_assessment,
          p.data_coverage_json -> 'evaluation_grade_confirmation_v1' AS grade_confirmation,
          p.data_coverage_json #> '{auto_dimension_scores,dimensions}' AS dimensions,
          p.data_coverage_json #>> '{new_products_score_facts_v2,market_score}' AS market_score,
          p.data_coverage_json #>> '{evaluation_formal_trigger,status}' AS formal_status,
          p.data_coverage_json ? 'auto_dimension_scores' AS has_auto
        FROM wanted w
        LEFT JOIN biz_new_product_registry r
          ON r.source_account_ref=w.a AND r.store_id=w.s AND r.item_id=w.i
        LEFT JOIN biz_new_product_performance_current p ON p.registry_id=r.id
    """),
            {"wants": json.dumps([{"a": a, "s": s, "i": i} for a, s, i in keys])},
        )
        .mappings()
        .all()
    )
    proofs = {(str(x["a"]), str(x["s"]), str(x["i"])): x for x in decision}
    decision_ms = int((time.monotonic() - started) * 1000) - mart_ms

    sku_keys = sorted(
        {(str(r["source_account_ref"]), str(r["local_sku"])) for r in rows if r["local_sku"]}
    )
    owners = {}
    if sku_keys:
        owner_rows = (
            source.execute(
                select(
                    PRODUCT_INFO_CURRENT.c.source_account_ref,
                    PRODUCT_INFO_CURRENT.c.lingxing_sku_code,
                    func.max(PRODUCT_INFO_CURRENT.c.owner_name).label("owner_name"),
                    func.max(PRODUCT_INFO_CURRENT.c.product_developer_name).label(
                        "product_developer_name"
                    ),
                )
                .where(
                    tuple_(
                        PRODUCT_INFO_CURRENT.c.source_account_ref,
                        PRODUCT_INFO_CURRENT.c.lingxing_sku_code,
                    ).in_(sku_keys)
                )
                .group_by(
                    PRODUCT_INFO_CURRENT.c.source_account_ref,
                    PRODUCT_INFO_CURRENT.c.lingxing_sku_code,
                )
            )
            .mappings()
            .all()
        )
        owners = {
            (str(x["source_account_ref"]), str(x["lingxing_sku_code"])): x for x in owner_rows
        }

    result = []
    for r in rows:
        key = (str(r["source_account_ref"]), str(r["store_id"]), str(r["item_id"]))
        p = proofs.get(key) or {}
        raw_start = r["listing_start_at_utc"]
        # For status the date is only a presence witness; never infer WFS
        # first-stock from an order or from a synthetic default date.
        listing_day = p.get("listing_date_la")
        if listing_day is None and isinstance(raw_start, datetime):
            listing_day = raw_start.astimezone(LA).date() if raw_start.tzinfo else raw_start.date()
        first_wfs = p.get("first_wfs_available_date_la") or (
            r.get("source_first_wfs") if has_locked else None
        )
        formal = p.get("formal_status") == "completed" and bool(p.get("has_auto"))
        coverage = (
            {"evaluation_formal_trigger": {"status": "completed"}, "auto_dimension_scores": {}}
            if formal
            else {}
        )
        if isinstance(p.get("operator_assessment"), dict):
            coverage["operator_assessment_v1"] = p["operator_assessment"]
        if isinstance(p.get("grade_confirmation"), dict):
            coverage["evaluation_grade_confirmation_v1"] = p["grade_confirmation"]
        status = evaluation_status(
            listing_date=listing_day,
            first_wfs=first_wfs,
            coverage=coverage,
            grade=p.get("grade"),
            total=p.get("score"),
        )
        grade = (
            str(p["grade"])
            if p.get("grade") in _GRADES and p.get("score") is not None
            else "pending"
        )
        owner_row = owners.get((key[0], str(r["local_sku"]))) if r["local_sku"] else None
        owner_name = owner_row["owner_name"] if owner_row else None
        developer_name = owner_row["product_developer_name"] if owner_row else None
        result.append(
            {
                "identity": key,
                "status": status,
                "grade": grade,
                "owner": str(owner_name) if owner_name else "未分配",
                "developer": str(developer_name) if developer_name else "未分配",
                "first_wfs": first_wfs,
                "launch_day": listing_day,
                "category": r["category_raw"],
                "sku": r["local_sku"],
                "name": r["local_name"] or r["title"],
                "total": str(p["score"]) if p.get("score") is not None else None,
                "dimensions": p.get("dimensions"),
                "market_score": p.get("market_score"),
            }
        )
    _LOGGER.info(
        "new_product_scope_summary rows=%d mart_ms=%d decision_ms=%d total_ms=%d",
        len(result),
        mart_ms,
        decision_ms,
        int((time.monotonic() - started) * 1000),
    )
    return result


def summary(source, db, accounts: frozenset[str]) -> dict:
    rows = scoped_projection(source, db, accounts)
    states = Counter(r["status"] for r in rows)
    owners = Counter(r["owner"] for r in rows)
    grades = Counter(r["grade"] for r in rows)
    return {
        "counts": {
            "all": len(rows),
            "evaluating": states["测评中"],
            "market": states["待市场评分"],
            "pending_grade_confirmation": states["待等级确认"],
            "pending_confirmation": states["待测评确认"],
            "passed": states["测评通过"],
            "failed": states["测评未通过"],
        },
        "status_options": [
            {"value": s, "label": s, "count": states[s]} for s in _STATUSES if states[s] > 0
        ],
        "owner_options": [{"value": o, "label": o, "count": c} for o, c in sorted(owners.items())],
        "rating_options": [
            {"value": g, "label": ("待评分" if g == "pending" else g + " 级"), "count": grades[g]}
            for g in (*_GRADES, "pending")
        ],
    }


def matching_identities(
    source,
    db,
    accounts: frozenset[str],
    *,
    statuses: str = "",
    owners: str = "",
    ratings: str = "",
    owner_keyword: str = "",
) -> list[tuple[str, str, str]]:
    status_set = set(filter(None, (s.strip() for s in statuses.split(","))))
    owner_set = set(filter(None, (s.strip() for s in owners.split(","))))
    rating_set = set(filter(None, (s.strip() for s in ratings.split(","))))
    needle = owner_keyword.strip().casefold()
    if statuses == "__none__":
        return []
    if status_set - set(_STATUSES) or rating_set - set((*_GRADES, "pending")):
        raise ValueError("NEW_PRODUCT_INVALID_PERFORMANCE_FILTER")
    return [
        r["identity"]
        for r in scoped_projection(source, db, accounts)
        if (not status_set or r["status"] in status_set)
        and (not owner_set or r["owner"] in owner_set)
        and (not rating_set or r["grade"] in rating_set)
        and (not needle or needle in r["owner"].casefold())
    ]


# NP_BOARD_INDEPENDENT_CN_20261119: read-only server statistics.
def _board_group(items: list[dict], title: str) -> dict:
    from decimal import Decimal

    scored = [r for r in items if r["status"] in ("测评通过", "测评未通过")]
    passed = [r for r in scored if r["status"] == "测评通过"]
    high = [r for r in scored if r["grade"] in ("S", "A")]
    valid_scores = [Decimal(str(r["total"])) for r in scored if r["total"] is not None]
    return {
        "name": title,
        "count": len(items),
        "completed": len(scored),
        "passed": len(passed),
        "rate": f"{len(passed) / len(scored) * 100:.1f}%" if scored else "—",
        "highRate": f"{len(high) / len(scored) * 100:.1f}%" if scored else "—",
        "avg": str((sum(valid_scores) / len(valid_scores)).quantize(Decimal("0.01")))
        if valid_scores
        else "—",
        "grades": {g: sum(r["grade"] == g for r in scored) for g in _GRADES},
    }


def board_summary(source, db, accounts: frozenset[str], *, start_date, end_date, remind_days=30):
    """One scoped MART+decision projection, never a live item/detail scoring loop."""
    if not isinstance(start_date, date) or not isinstance(end_date, date) or start_date > end_date:
        raise ValueError("NP_BOARD_DATE_RANGE_INVALID")
    today = datetime.now(LA).date()
    allowed = {"测评中", "待市场评分", "待等级确认", "待测评确认", "测评通过", "测评未通过"}
    rows = [
        r
        for r in scoped_projection(source, db, accounts)
        if r["first_wfs"] is not None
        and start_date <= r["first_wfs"] <= end_date
        and r["status"] in allowed
    ]
    status = Counter(r["status"] for r in rows)
    completed = status["测评通过"] + status["测评未通过"]
    grades = {
        g: sum(r["grade"] == g for r in rows if r["status"] in ("测评通过", "测评未通过"))
        for g in _GRADES
    }
    reasons = {k: 0 for k in ("market", "speed", "ad", "profit", "trust")}
    for r in rows:
        if r["status"] != "测评未通过":
            continue
        dimensions = dict(r.get("dimensions") or {})
        if r.get("market_score") is not None:
            dimensions["market"] = r["market_score"]
        numeric = []
        for key in reasons:
            value = dimensions.get(key)
            if value is None:
                continue
            try:
                from decimal import Decimal

                score = Decimal(str(value))
                if score.is_finite() and 0 <= score <= 10:
                    numeric.append((score, key))
            except (ValueError, ArithmeticError, TypeError):
                continue
        if numeric:
            reasons[min(numeric)[1]] += 1
    category_groups = {}
    category_paths = {}
    developer_groups = {}
    unresolved = 0
    source_missing = 0
    unmapped_raw_categories: set[str] = set()
    for r in rows:
        raw = str(r.get("category") or "").strip()
        # NP_BOARD_BUSINESS_CATEGORY_V5: original taxonomy remains attached.
        translated = translate_category(raw)
        category = business_category(raw)
        if not raw:
            source_missing += 1
        if translated == "待补充中文分类":
            unresolved += 1
            unmapped_raw_categories.add(raw)
        category_groups.setdefault(category, []).append(r)
        if raw:
            category_paths.setdefault(category, {})[raw] = category_path_detail(raw)
        developer_groups.setdefault(r["developer"], []).append(r)
    due = [
        r
        for r in rows
        if r["status"] == "待市场评分" and (today - r["first_wfs"]).days + 1 >= remind_days
    ]
    due.sort(key=lambda r: (r["first_wfs"], r["identity"]))
    return {
        "date_basis": "first_wfs_available_date_la",
        "status_basis": "latest_saved_evaluation",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "counts": {
            "total": len(rows),
            "evaluating": status["测评中"],
            "market": status["待市场评分"],
            "passed": status["测评通过"],
            "failed": status["测评未通过"],
            "completed": completed,
            "low_grade": grades["C"],
            "due": len(due),
        },
        "pass_rate": f"{status['测评通过'] / completed * 100:.1f}%" if completed else "—",
        "grades": grades,
        # These are lowest verified dimensions, never asserted root causes.
        "failure_dimensions": reasons,
        "categories": [
            {
                **_board_group(values, category_name),
                "subcategories": sorted(
                    category_paths.get(category_name, {}).values(),
                    key=lambda detail: (detail["label"], detail["raw"]),
                ),
            }
            for category_name, values in sorted(category_groups.items())
        ],
        "developers": [_board_group(v, k) for k, v in sorted(developer_groups.items())],
        "untranslated_categories": unresolved,
        "missing_source_categories": source_missing,
        "unmapped_raw_categories": sorted(unmapped_raw_categories),
        "reminders": [
            {
                "id": "::".join(r["identity"]),
                "sku": r["sku"] or "—",
                "name": r["name"] or "品名待同步",
                "developer": r["developer"],
                "days": (today - r["first_wfs"]).days + 1,
            }
            for r in due
        ],
    }
