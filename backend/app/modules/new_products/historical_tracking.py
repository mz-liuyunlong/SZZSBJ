"""Explicit historical tracking enrollment, independent of current sample scoring."""

from __future__ import annotations

from sqlalchemy import or_, select, tuple_

from .models import NewProductPerformanceCurrent, NewProductRegistry, NewProductTrackingCurrent

HISTORY_BLOCK = "historical_tracking_import_v1"
HISTORY_SOURCE = "manual_historical_import"
HISTORY_TAG = "代采测品"
HISTORY_GRADES = ("S", "A", "B", "C", "D")


def snapshots(db, accounts, keys=None):
    """Read enrollment from the decision DB, never from untrusted caller identity alone."""
    if not accounts or (keys is not None and not keys):
        return {}
    r, p, t = NewProductRegistry, NewProductPerformanceCurrent, NewProductTrackingCurrent
    stmt = (
        select(r.source_account_ref, r.store_id, r.item_id, p.data_coverage_json, t.initial_grade)
        .join(p, p.registry_id == r.id)
        .join(t, t.registry_id == r.id)
        .where(
            r.source_account_ref.in_(accounts),
            r.listing_source_tag == HISTORY_TAG,
            p.data_coverage_json.contains({HISTORY_BLOCK: {"source": HISTORY_SOURCE}}),
            t.initial_grade.in_(HISTORY_GRADES),
        )
    )
    if keys is not None:
        stmt = stmt.where(tuple_(r.source_account_ref, r.store_id, r.item_id).in_(sorted(keys)))
    result = {}
    for account, store, item, coverage, grade in db.execute(stmt).all():
        block = coverage.get(HISTORY_BLOCK)
        if isinstance(block, dict) and block.get("grade") == grade:
            result[(str(account), str(store), str(item))] = block
    return result


def listing_scope(mart, historical_keys=()):
    """Default scope is unchanged. Only explicitly enrolled exact keys extend tracking reads."""
    sample = mart.product_tags_json.contains([{"label": "小批量测品"}])
    if not historical_keys:
        return sample
    return or_(
        sample,
        tuple_(mart.source_account_ref, mart.store_id, mart.item_id).in_(sorted(historical_keys)),
    )


def overlay(row, snapshot):
    """Historical score is evidence, not a new-system automatic grade or purchase approval."""
    ev = row["evaluation"]
    dims = snapshot["dimensions"]
    ev.update(
        total=str(snapshot["total"]),
        grade=snapshot["grade"],
        rule_version=0,
        observation_state="historical_import",
        missing=[],
    )
    # Historical risk/supply is not the current trust metric. Keep it in raw evidence.
    ev["dimensions"] = {k: str(dims[k]) for k in ("market", "speed", "ad", "profit")}
    ev["dimensions"]["trust"] = None
    row["facts"][HISTORY_BLOCK] = snapshot
    row["facts"]["final_score_source"] = HISTORY_SOURCE
    row["suggested_qty"] = None
