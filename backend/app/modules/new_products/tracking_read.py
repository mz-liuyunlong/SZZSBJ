"""Read-only tracking summaries and paged rows from existing saved projections.

The source MART and the decision database can be different PostgreSQL targets.
No cross-database joins, live scoring, synchronous refreshes or writes occur here.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError

from .performance_list_scope import scoped_projection
from .service import NewProductService, local_preview_item_ids

LA = ZoneInfo("America/Los_Angeles")
GRADES = ("S", "A", "B", "C", "D", "Pass", "待评分")
BUCKETS = (
    "0–29天", "30–59天", "60–89天", "90–119天", "120–149天",
    "150–179天", "180天及以上", "无到货时间",
)
OUTCOMES = ("success", "observe", "optimize", "failure", "undecided")
MAX_ROWS = 5000


def _iso(value: date | str | None) -> str:
    return value.isoformat() if isinstance(value, date) else str(value or "")[:10]


def _days(start: str, end: str) -> int | None:
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (TypeError, ValueError):
        return None


def _bucket(row: dict, as_of: str) -> str:
    elapsed = _days(row["arrival"], as_of)
    if elapsed is None or elapsed < 0:
        return BUCKETS[-1]
    return BUCKETS[min(elapsed // 30, 6)]


def _outcome(row: dict) -> str:
    decision = row["tracking"]
    return {
        "打品成功": "success",
        "继续观察": "observe",
        "需要优化": "optimize",
        "打品失败": "failure",
    }.get(decision, "undecided")


def _rate(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def _saved_decisions(db: Session, keys: list[tuple[str, str, str]]) -> dict:
    """One bounded decision query per batch; no remote reads or N+1 lookups."""
    if not keys:
        return {}
    answer = {}
    statement = text("""
        WITH wanted AS (
          SELECT a,s,i FROM jsonb_to_recordset(CAST(:wanted AS jsonb))
          AS w(a text,s text,i text)
        )
        SELECT w.a,w.s,w.i,
               p.status AS purchase_status,p.approved_qty,
               COALESCE(p.suggested_qty,t.purchase_suggested_qty) AS suggested_qty,
               t.initial_grade,t.tracking_started_date_la,
               t.final_result,t.tracking_status,
               d.decision AS manual_decision
        FROM wanted w
        LEFT JOIN biz_new_product_registry r
          ON r.source_account_ref=w.a AND r.store_id=w.s AND r.item_id=w.i
        LEFT JOIN biz_new_product_tracking_current t ON t.registry_id=r.id
        LEFT JOIN LATERAL (
          SELECT status,approved_qty,suggested_qty FROM biz_new_product_purchase_applications p
          WHERE p.source_account_ref=w.a AND p.store_id=w.s AND p.item_id=w.i
          ORDER BY p.created_at DESC,p.id DESC LIMIT 1
        ) p ON TRUE
        LEFT JOIN biz_new_product_tracking_decisions d
          ON d.source_account_ref=w.a AND d.store_id=w.s AND d.item_id=w.i
    """)
    for offset in range(0, len(keys), 200):
        batch = keys[offset : offset + 200]
        params = {"wanted": json.dumps([{"a": a, "s": s, "i": i} for a, s, i in batch])}
        for row in db.execute(statement, params).mappings():
            answer[(row["a"], row["s"], row["i"])] = dict(row)
    return answer


def _projection(source: Session, db: Session, accounts: frozenset[str]) -> list[dict]:
    """Small in-memory metadata only, never full item facts or detail JSON."""
    if not accounts:
        return []
    summary = scoped_projection(source, db, accounts)
    if len(summary) > MAX_ROWS:
        raise ApiError(code="NP_TRACKING_SCOPE_TOO_LARGE", status_code=422)
    preview = local_preview_item_ids()
    if preview is not None:
        summary = [row for row in summary if row["identity"][2] in preview]
    keys = [tuple(item["identity"]) for item in summary]
    decisions = _saved_decisions(db, keys)
    result = []
    for item in summary:
        key = tuple(item["identity"])
        saved = decisions.get(key, {})
        purchase_status = saved.get("purchase_status")
        suggested_qty = saved.get("suggested_qty")
        approved_qty = int(saved.get("approved_qty") or 0)
        arrival = _iso(item.get("first_wfs"))
        launch = _iso(item.get("launch_day"))
        initial = saved.get("initial_grade")
        grade = initial if initial in GRADES else item["grade"]
        if grade not in GRADES:
            grade = "待评分"
        manual = saved.get("manual_decision")
        final = saved.get("final_result")
        # Final human-reviewed outcome takes precedence over mutable status.
        if final in ("打品成功", "打品失败"):
            decision = final
        elif manual:
            decision = manual
        else:
            decision = "未判定" if arrival else "等待开售"
        if not (approved_qty > 0 or purchase_status == "approved" or
                decision not in ("等待开售", "未判定", "")):
            continue
        category = str(item.get("category") or "").strip() or "未分类"
        result.append({
            "identity": key, "id": "::".join(key), "item": key[2],
            "sku": str(item.get("sku") or "—"),
            "name": str(item.get("name") or "品名待同步"),
            "owner": str(item.get("owner") or "未分配"),
            "category": category,
            # Only verified stored secondary taxonomy can be used; do not invent one.
            "secondary": None,
            "grade": grade, "has_initial_grade": initial in GRADES,
            "suggested_qty": int(suggested_qty) if suggested_qty is not None else None,
            "arrival": arrival, "launch": launch,
            "entry": arrival or launch,
            "tracking": decision,
        })
    return result


def _window(rows: list[dict], start: str, end: str) -> list[dict]:
    return [r for r in rows if r["entry"] and start <= r["entry"] <= end]


def _group(rows: list[dict], kind: str) -> list[dict]:
    by_name: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_name[row[kind]].append(row)
    groups = []
    for name, members in by_name.items():
        success = sum(_outcome(r) == "success" for r in members)
        failed = sum(_outcome(r) == "failure" for r in members)
        entry = {"key": name, "total": len(members), "success": success,
                 "failed": failed, "pending": len(members) - success - failed,
                 "rate": _rate(success, success + failed)}
        if kind == "owner":
            entry["name"] = name
        else:
            entry.update(
                category=name,
                recommendation="样本不足" if success + failed < 5 else "待配置",
            )
        groups.append(entry)
    return sorted(groups, key=lambda r: (-r["total"], str(r["key"])))


def board_summary(source: Session, db: Session, accounts: frozenset[str],
                  start_date: date, end_date: date) -> dict:
    if start_date > end_date:
        raise ApiError(code="NP_TRACKING_DATE_RANGE_INVALID", status_code=422)
    start, end = start_date.isoformat(), end_date.isoformat()
    pool = _window(_projection(source, db, accounts), start, end)
    success = [r for r in pool if _outcome(r) == "success"]
    failed = [r for r in pool if _outcome(r) == "failure"]
    due = [r for r in pool if (_days(r["arrival"], end) or -1) > 45
           and _outcome(r) not in ("success", "failure")]
    due.sort(key=lambda r: (r["arrival"], r["id"]))
    observations = []
    for label in BUCKETS:
        selected = [r for r in pool if _bucket(r, end) == label]
        kinds = Counter(_outcome(r) for r in selected)
        observations.append({
            "key": label, "label": label, "total": len(selected),
            "success": kinds["success"], "failed": kinds["failure"],
            "stable": kinds["observe"], "pending": kinds["optimize"] +
            sum(r["tracking"] == "等待开售" for r in selected),
            "unknown": sum(r["tracking"] == "未判定" for r in selected),
            "rate": _rate(kinds["success"], kinds["success"] + kinds["failure"]),
        })
    return {
        "date_basis": "first_wfs_or_existing_listing_start",
        "status_basis": "current_saved_tracking_not_historical_snapshot",
        "start_date": start, "end_date": end,
        "counts": {"pool": len(pool), "success": len(success), "failed": len(failed),
                   "failed_categories": len({r["category"] for r in failed
                                             if r["category"] != "未分类"}),
                   "due": len(due)},
        "success_rate": _rate(len(success), len(pool)),
        "grades": [{"key": grade, "grade": grade,
                    "total": sum(r["grade"] == grade for r in pool)} for grade in GRADES],
        "owners": _group(pool, "owner"),
        "categories": _group(pool, "category"),
        "secondary": [], "no_secondary": len(pool),
        "observations": observations,
        "has_stored_initial_grade": any(r["has_initial_grade"] for r in pool),
        # Reminders contain only the minimum fields required by the existing UI.
        "due": [{"id": r["id"], "item": r["item"], "sku": r["sku"],
                 "name": r["name"], "owner": r["owner"], "arrival": r["arrival"]}
                for r in due[:100]],
    }


def _drill_match(row: dict, kind: str, value: str, parent: str, end: str) -> bool:
    if kind == "category":
        return row["category"] == value
    if kind == "secondary":
        return row["secondary"] == value and (not parent or row["category"] == parent)
    if kind == "observation":
        return _bucket(row, end) == value
    return True


def detail_list(source: Session, db: Session, accounts: frozenset[str], *,
                page: int, page_size: int, keyword: str, owners: str, grades: str,
                outcome: str, drill_kind: str, drill_value: str,
                parent_category: str, start_date: date | None,
                end_date: date | None) -> dict:
    if bool(start_date) != bool(end_date) or (start_date and end_date and start_date > end_date):
        raise ApiError(code="NP_TRACKING_DATE_RANGE_INVALID", status_code=422)
    kinds = ("", "all", "owner", "grade", "category", "secondary", "observation", "item")
    if drill_kind not in kinds:
        raise ApiError(code="NP_TRACKING_DRILL_INVALID", status_code=422)
    if outcome not in ("all", *OUTCOMES):
        raise ApiError(code="NP_TRACKING_OUTCOME_INVALID", status_code=422)
    if page_size not in (20, 50) or page < 1:
        raise ApiError(code="NP_TRACKING_PAGE_INVALID", status_code=422)
    pool = _projection(source, db, accounts)
    if start_date and end_date:
        pool = _window(pool, _iso(start_date), _iso(end_date))
    if drill_kind in ("category", "secondary", "observation"):
        end = _iso(end_date) if end_date else datetime.now(LA).date().isoformat()
        pool = [r for r in pool if _drill_match(r, drill_kind, drill_value, parent_category, end)]
    owner_options = [{"value": row["name"], "label": row["name"], "count": row["total"]}
                     for row in _group(pool, "owner")]
    grade_options = [{"value": grade, "label": ("待评分" if grade == "待评分" else grade + " 级"),
                      "count": sum(r["grade"] == grade for r in pool)} for grade in GRADES]
    owners_set = {i.strip() for i in owners.split(",") if i.strip()}
    grades_set = {i.strip() for i in grades.split(",") if i.strip()}
    needle = keyword.strip().casefold()
    filtered = [r for r in pool if
                (not owners_set or r["owner"] in owners_set) and
                (not grades_set or r["grade"] in grades_set) and
                (not needle or needle in " ".join((r["item"], r["sku"], r["name"])).casefold())]
    counts = Counter(_outcome(r) for r in filtered)
    counts_dict = {"all": len(filtered), **{o: counts[o] for o in OUTCOMES}}
    chosen = [r for r in filtered if outcome == "all" or _outcome(r) == outcome]
    chosen.sort(key=lambda r: r["id"])
    total = len(chosen)
    page_rows = chosen[(page - 1) * page_size : page * page_size]
    if not page_rows:
        return {"items": [], "total": total, "page": page, "page_size": page_size,
                "counts": counts_dict, "owner_options": owner_options,
                "grade_options": grade_options,
                "status_basis": "current_saved_tracking_not_historical_snapshot"}
    # Reuse existing persisted-only bounded Listing DTO and workflow overlay;
    # fetching the full item payload is restricted to one page of exact identities.
    keys = [tuple(r["identity"]) for r in page_rows]
    service = NewProductService(db, read_session=source)
    q = SimpleNamespace(page=1, page_size=page_size, store_id="", owner="", keyword="",
                        search_field="item_id", status="")
    result = service._list_saved(accounts, q, item_keys=keys)
    from .evaluation_workflow import decorate_page
    result = decorate_page(db, result)
    items_by_key = {tuple(str(x["listing"][k]) for k in
                          ("source_account_ref", "store_id", "item_id")): x
                    for x in result["items"]}
    ordered = []
    for row in page_rows:
        saved = items_by_key.get(tuple(row["identity"]))
        if saved is None:
            # Concurrent source changes must not create inconsistent totals.
            raise ApiError(code="NP_TRACKING_PAGE_STALE", status_code=409)
        saved["tracking_final_result"] = row["tracking"] if row["tracking"] in (
            "打品成功", "打品失败") else saved.get("tracking_final_result")
        saved["tracking_decision"] = row["tracking"]
        saved["tracking_page_decision"] = row["tracking"]
        saved["tracking_initial_grade"] = row["grade"]
        saved["suggested_qty"] = row.get("suggested_qty")
        ordered.append(saved)
    return {"items": ordered, "total": total, "page": page, "page_size": page_size,
            "counts": counts_dict, "owner_options": owner_options,
            "grade_options": grade_options,
            "status_basis": "current_saved_tracking_not_historical_snapshot"}
