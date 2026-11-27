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

from sqlalchemy import func, or_, select, text, tuple_

from app.core.api import ApiError
from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.data_pages.repository import LISTING_WFS_LA_LOCKED, PRODUCT_INFO_CURRENT
from app.modules.walmart_monitor.models import WalmartMonitorListingCurrent

from .category_zh import business_category, category_path_detail, translate_category
from .evaluation_policy import evaluation_status
from .historical_tracking import listing_scope

SAMPLE_TAG = "小批量测品"
LA = ZoneInfo("America/Los_Angeles")
_STATUSES = ("待到货", "测评中", "待市场评分", "待等级确认", "待测评确认", "测评通过", "测评未通过")
_FLOW_GROUPS = {
    "evaluating": ("测评中",),
    "pending": ("待市场评分", "待等级确认", "待测评确认"),
    "passed": ("待申请采购", "采购审批中", "采购已批准", "采购已驳回"),
    "failed": ("测评未通过", "复核审批中", "待重新核算", "复核已驳回"),
}
_FLOW_STATUSES = ("待到货",) + tuple(s for group in _FLOW_GROUPS.values() for s in group)
_FLOW_PREFIX = "flow:"


def flow_status(
    status, purchase_status=None, review_status=None, recheck_required=False, *, first_wfs=None
):
    """Read-only projection; assessment conclusion always takes precedence."""
    # Listing launch alone does not establish the first WFS availability.
    if status == "测评中" and first_wfs is None:
        return "待到货"
    if status == "测评通过":
        return {"submitted": "采购审批中", "approved": "采购已批准", "rejected": "采购已驳回"}.get(
            purchase_status, "待申请采购"
        )
    if status == "测评未通过":
        if review_status in ("submitted", "info_required"):
            return "复核审批中"
        if review_status == "approved" and recheck_required:
            return "待重新核算"
        if review_status == "rejected":
            return "复核已驳回"
    return status


_GRADES = ("S", "A", "B", "C", "D", "Pass")
_LOGGER = logging.getLogger(__name__)


def scoped_projection(
    source,
    db,
    accounts: frozenset[str],
    *,
    historical_keys=(),
    include_owners=True,
    include_board_details=True,
    include_effective_grades=False,
    keyword="",
    search_field="sku",
) -> list[dict]:
    """Base assessment projection; approval states are loaded separately on demand."""
    if not accounts:
        return []
    started = time.monotonic()
    m = ListingManagementCurrentMart
    monitor = WalmartMonitorListingCurrent
    stmt = select(
        m.source_account_ref,
        m.store_id,
        m.item_id,
        m.local_sku,
        m.listing_start_at_utc,
    ).where(m.source_account_ref.in_(accounts), listing_scope(m, historical_keys))
    if keyword.strip():
        pattern = f"%{keyword.strip()}%"
        column = {
            "sku": m.local_sku,
            "msku": m.msku,
            "item_id": m.item_id,
            "title": m.title,
        }[search_field]
        predicate = (
            or_(m.local_name.ilike(pattern), column.ilike(pattern))
            if search_field == "title"
            else column.ilike(pattern)
        )
        stmt = stmt.add_columns(func.coalesce(predicate, False).label("keyword_match"))
    if include_board_details:
        stmt = stmt.add_columns(
            m.local_name,
            m.title,
            func.coalesce(
                func.nullif(func.btrim(monitor.category), ""),
                func.nullif(func.btrim(m.category), ""),
            ).label("category_raw"),
        ).outerjoin(
            monitor,
            (monitor.source_account_ref == m.source_account_ref)
            & (monitor.store_id == m.store_id)
            & (monitor.item_id == m.item_id),
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
    # The list filters and cards need the assessment state, not the board's
    # category breakdown or dimension evidence. Keep board/tracking reads intact.
    board_fields = (
        """
          p.data_coverage_json #> '{auto_dimension_scores,dimensions}' AS dimensions,
          p.data_coverage_json #>> '{new_products_score_facts_v2,market_score}' AS market_score,
    """
        if include_board_details
        else ""
    )
    correction_fields = (
        """
          CASE WHEN p.data_coverage_json #>> '{evaluation_grade_confirmation_v1,status}'
            = 'pending' THEN p.data_coverage_json -> 'operator_score_correction_v1'
          END AS score_correction,
          CASE WHEN p.data_coverage_json #>> '{evaluation_grade_confirmation_v1,status}'
            = 'pending' THEN p.data_coverage_json -> 'evaluation_final_snapshot'
          END AS correction_final,
        """
        if include_effective_grades
        else ""
    )
    decision = (
        db.execute(
            text(
                """
        WITH wanted AS (
          SELECT a,s,i FROM jsonb_to_recordset(CAST(:wants AS jsonb))
          AS w(a text,s text,i text)
        )
        SELECT w.a,w.s,w.i,r.id::text AS registry_ref,r.listing_date_la,
          p.first_wfs_available_date_la, p.score,p.grade,
          p.data_coverage_json -> 'operator_assessment_v1' AS operator_assessment,
          p.data_coverage_json -> 'evaluation_grade_confirmation_v1' AS grade_confirmation,
          """
                + board_fields
                + correction_fields
                + """
          p.data_coverage_json #>> '{evaluation_formal_trigger,status}' AS formal_status,
          p.data_coverage_json ? 'auto_dimension_scores' AS has_auto,
          p.data_coverage_json #>> '{evaluation_recheck_required,status}' AS recheck_status
        FROM wanted w
        LEFT JOIN biz_new_product_registry r
          ON r.source_account_ref=w.a AND r.store_id=w.s AND r.item_id=w.i
        LEFT JOIN biz_new_product_performance_current p ON p.registry_id=r.id
    """
            ),
            {"wants": json.dumps([{"a": a, "s": s, "i": i} for a, s, i in keys])},
        )
        .mappings()
        .all()
    )
    proofs = {(str(x["a"]), str(x["s"]), str(x["i"])): x for x in decision}
    decision_ms = int((time.monotonic() - started) * 1000) - mart_ms

    owner_started = time.monotonic()
    sku_keys = sorted(
        {(str(r["source_account_ref"]), str(r["local_sku"])) for r in rows if r["local_sku"]}
    )
    owners = {}
    if include_owners and sku_keys:
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

    owner_ms = int((time.monotonic() - owner_started) * 1000)
    result = []
    correction_config = None
    if include_effective_grades and any(
        isinstance(p.get("score_correction"), dict) for p in proofs.values()
    ):
        from .evaluation_workflow import _config

        correction_config, _ = _config(db)
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
        if correction_config is not None and isinstance(p.get("score_correction"), dict):
            grade = _pending_effective_grade(p, correction_config) or grade
        owner_row = owners.get((key[0], str(r["local_sku"]))) if r["local_sku"] else None
        owner_name = owner_row["owner_name"] if owner_row else None
        developer_name = owner_row["product_developer_name"] if owner_row else None
        result.append(
            {
                "identity": key,
                "status": status,
                "flow_status": flow_status(status, first_wfs=first_wfs),
                "_registry_ref": p.get("registry_ref"),
                "_recheck_required": p.get("recheck_status")
                == "awaiting_verified_source_correction",
                "grade": grade,
                "keyword_match": bool(r.get("keyword_match")) if keyword.strip() else True,
                "owner": str(owner_name) if owner_name else "未分配",
                "developer": str(developer_name) if developer_name else "未分配",
                "first_wfs": first_wfs,
                "launch_day": listing_day,
                "category": r.get("category_raw"),
                "sku": r["local_sku"],
                "name": r.get("local_name") or r.get("title"),
                "total": str(p["score"]) if p.get("score") is not None else None,
                "dimensions": p.get("dimensions"),
                "market_score": p.get("market_score"),
            }
        )
    _LOGGER.info(
        (
            "new_product_scope_summary rows=%d mart_ms=%d decision_ms=%d owner_ms=%d "
            "total_ms=%d board_details=%s"
        ),
        len(result),
        mart_ms,
        decision_ms,
        owner_ms,
        int((time.monotonic() - started) * 1000),
        include_board_details,
    )
    return result


def _attach_flow_statuses(db, rows, *, purchase=True, review=True):
    """At most two set-based queries, only for relevant scoped terminal rows."""
    purchase_rows = [r for r in rows if r["status"] == "测评通过"] if purchase else []
    review_rows = (
        [r for r in rows if r["status"] == "测评未通过" and r.get("_registry_ref")]
        if review
        else []
    )
    if purchase_rows:
        keys = sorted({tuple(r["identity"]) for r in purchase_rows})
        records = (
            db.execute(
                text("""
            WITH wanted AS (
              SELECT a,s,i FROM jsonb_to_recordset(CAST(:wants AS jsonb)) AS w(a text,s text,i text)
            )
            SELECT DISTINCT ON (pa.source_account_ref,pa.store_id,pa.item_id)
                pa.source_account_ref AS a,pa.store_id AS s,pa.item_id AS i,pa.status
            FROM biz_new_product_purchase_applications pa
            JOIN wanted w ON pa.source_account_ref=w.a AND pa.store_id=w.s AND pa.item_id=w.i
            ORDER BY pa.source_account_ref,pa.store_id,pa.item_id,pa.created_at DESC,pa.id DESC
        """),
                {"wants": json.dumps([{"a": a, "s": s, "i": i} for a, s, i in keys])},
            )
            .mappings()
            .all()
        )
        latest = {(r["a"], r["s"], r["i"]): r["status"] for r in records}
        for r in purchase_rows:
            r["flow_status"] = flow_status(
                r["status"], purchase_status=latest.get(tuple(r["identity"]))
            )
    if review_rows:
        refs = sorted({r["_registry_ref"] for r in review_rows})
        records = (
            db.execute(
                text("""
            WITH wanted AS (SELECT jsonb_array_elements_text(CAST(:refs AS jsonb)) AS ref)
            SELECT DISTINCT ON (a.business_ref) a.business_ref,a.status
            FROM app_approval_requests a JOIN wanted w ON a.business_ref=w.ref
            WHERE a.approval_type='new_product_evaluation_review'
            ORDER BY a.business_ref,a.submitted_at DESC,a.id DESC
        """),
                {"refs": json.dumps(refs)},
            )
            .mappings()
            .all()
        )
        latest = {r["business_ref"]: r["status"] for r in records}
        for r in review_rows:
            r["flow_status"] = flow_status(
                r["status"],
                review_status=latest.get(r["_registry_ref"]),
                recheck_required=r["_recheck_required"],
            )


def _needs_flow_lookup(status_set, group, base_status):
    selected = {_FLOW_PREFIX + s for s in _FLOW_GROUPS[group]}
    # Selecting every substate (or the legacy base status) is equivalent to the
    # base assessment; no approval lookup can change membership.
    return (
        base_status not in status_set and bool(selected & status_set) and not selected <= status_set
    )


# NP_FIRST_WFS_DATE_FILTER_V1
def _validate_first_wfs_range(start_date: date | None, end_date: date | None) -> None:
    if (start_date is None) != (end_date is None) or (
        start_date is not None and end_date is not None and start_date > end_date
    ):
        raise ApiError(
            code="NP_FIRST_WFS_DATE_RANGE_INVALID",
            status_code=422,
            message="请选择完整的WFS首次可售日期范围，开始日期不得晚于结束日期",
        )


def _first_wfs_projection(
    source,
    db,
    accounts,
    start_date=None,
    end_date=None,
    *,
    include_owners=True,
    include_effective_grades=False,
    keyword="",
    search_field="sku",
):
    """Filter the same scoped LA-date evidence used by the performance board.

    No selected range retains unknown first-stock dates. With a range, unknown
    first-stock dates are excluded rather than inferred from orders or launch.
    """
    _validate_first_wfs_range(start_date, end_date)
    rows = scoped_projection(
        source,
        db,
        accounts,
        include_owners=include_owners,
        include_board_details=False,
        include_effective_grades=include_effective_grades,
        keyword=keyword,
        search_field=search_field,
    )
    if start_date is None:
        return rows
    return [
        row
        for row in rows
        if row["first_wfs"] is not None and start_date <= row["first_wfs"] <= end_date
    ]


# NP_LINKED_FACETS_V1: use the same saved correction overlay as decorate_page.
def _pending_effective_grade(proof, config):
    from .score_corrections import overlay

    original = proof.get("grade")
    block = proof.get("score_correction")
    final = proof.get("correction_final")
    if (
        not isinstance(block, dict)
        or not isinstance(final, dict)
        or final.get("grade") != original
        or proof.get("score") is None
    ):
        return original
    row = {
        "evaluation": {
            "grade": original,
            "total": str(proof["score"]),
            "dimensions": final.get("dimensions"),
            "rule_version": final.get("rule_version"),
            "observation_state": "scored",
        }
    }
    if overlay(row, block, config, risk_evaluation=final.get("risk_evaluation"), require_risk=True):
        return row["evaluation"]["grade"]
    return original


def _split_filter(value):
    return {part.strip() for part in value.split(",") if part.strip()}


def _row_flow(row):
    return row.get("flow_status") or flow_status(row["status"], first_wfs=row.get("first_wfs"))


def _matches_status(row, selected):
    return not selected or row["status"] in selected or _FLOW_PREFIX + _row_flow(row) in selected


def _facet_counts(rows, *, phase, statuses, owners, ratings, owner_keyword):
    selected_statuses = _split_filter(statuses)
    selected_owners = _split_filter(owners)
    selected_ratings = _split_filter(ratings)
    needle = owner_keyword.strip().casefold()
    allowed_flow = set(_FLOW_GROUPS.get(phase, _FLOW_STATUSES))
    flow_counts, owner_counts, grade_counts = Counter(), Counter(), Counter()
    for row in rows:
        flow = _row_flow(row)
        if flow not in allowed_flow or not row.get("keyword_match", True):
            continue
        if needle and needle not in row["owner"].casefold():
            continue
        status_ok = _matches_status(row, selected_statuses)
        owner_ok = not selected_owners or row["owner"] in selected_owners
        rating_ok = not selected_ratings or row["grade"] in selected_ratings
        if owner_ok and rating_ok:
            flow_counts[flow] += 1
        if status_ok and rating_ok:
            owner_counts[row["owner"]] += 1
        if status_ok and owner_ok:
            grade_counts[row["grade"]] += 1
    # Keep selected zero-match values available for deselection.
    for owner in selected_owners:
        owner_counts.setdefault(owner, 0)
    return flow_counts, owner_counts, grade_counts


def summary(
    source,
    db,
    accounts: frozenset[str],
    *,
    start_date=None,
    end_date=None,
    phase="all",
    statuses="",
    owners="",
    ratings="",
    owner_keyword="",
    keyword="",
    search_field="sku",
) -> dict:
    started = time.monotonic()
    rows = _first_wfs_projection(
        source,
        db,
        accounts,
        start_date,
        end_date,
        include_effective_grades=True,
        keyword=keyword,
        search_field=search_field,
    )
    flow_started = time.monotonic()
    _attach_flow_statuses(db, rows)
    _LOGGER.info(
        "new_product_summary_full rows=%d workflow_ms=%d total_ms=%d",
        len(rows),
        int((time.monotonic() - flow_started) * 1000),
        int((time.monotonic() - started) * 1000),
    )
    states = Counter(r["status"] for r in rows)
    flow_counts = Counter(
        r.get("flow_status") or flow_status(r["status"], first_wfs=r.get("first_wfs")) for r in rows
    )
    facet_flows, facet_owners, grades = _facet_counts(
        rows,
        phase=phase,
        statuses=statuses,
        owners=owners,
        ratings=ratings,
        owner_keyword=owner_keyword,
    )
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
        # Preserve the existing evaluation counts/options for other callers.
        "stage_counts": {
            "all": len(rows),
            "evaluating": flow_counts["测评中"],
            "pending": states["待市场评分"] + states["待等级确认"] + states["待测评确认"],
            "passed": states["测评通过"],
            "failed": states["测评未通过"],
        },
        "flow_status_options": [
            {"value": s, "label": s, "count": facet_flows[s]} for s in _FLOW_STATUSES
        ],
        "status_options": [
            {"value": s, "label": s, "count": states[s]} for s in _STATUSES if states[s] > 0
        ],
        "owner_options": [
            {"value": o, "label": o, "count": c} for o, c in sorted(facet_owners.items())
        ],
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
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[tuple[str, str, str]]:
    _validate_first_wfs_range(start_date, end_date)
    status_set = set(filter(None, (s.strip() for s in statuses.split(","))))
    owner_set = set(filter(None, (s.strip() for s in owners.split(","))))
    rating_set = set(filter(None, (s.strip() for s in ratings.split(","))))
    needle = owner_keyword.strip().casefold()
    if statuses == "__none__":
        return []
    # Unprefixed values retain the legacy evaluation filter contract.
    allowed_statuses = set(_STATUSES) | {_FLOW_PREFIX + s for s in _FLOW_STATUSES}
    if status_set - allowed_statuses or rating_set - set((*_GRADES, "pending")):
        raise ValueError("NEW_PRODUCT_INVALID_PERFORMANCE_FILTER")
    rows = [
        r
        for r in _first_wfs_projection(
            source,
            db,
            accounts,
            start_date,
            end_date,
            include_owners=bool(owner_set or needle),
            include_effective_grades=bool(rating_set),
        )
        if (not owner_set or r["owner"] in owner_set)
        and (not rating_set or r["grade"] in rating_set)
        and (not needle or needle in r["owner"].casefold())
    ]
    purchase = _needs_flow_lookup(status_set, "passed", "测评通过")
    review = _needs_flow_lookup(status_set, "failed", "测评未通过")
    if purchase or review:
        _attach_flow_statuses(db, rows, purchase=purchase, review=review)
    return [
        r["identity"]
        for r in rows
        if (
            not status_set
            or r["status"] in status_set
            or _FLOW_PREFIX
            + (r.get("flow_status") or flow_status(r["status"], first_wfs=r.get("first_wfs")))
            in status_set
        )
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
