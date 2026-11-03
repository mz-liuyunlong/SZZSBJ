"""Stable business keys (PRP §8.9) and content hashes (PRP §8.1)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal

from .money import q4

# store_id of 待指定 / order-review rows for movements whose Lingxing store_code maps to no
# store (PRP §8.4).  Never NULL (keeps the unique keys effective) and never a real store:
# APIs must keep it out of store lists / filters and show it only to all-store finance users.
UNMAPPED_STORE_ID = "__unmapped__"
RECONCILE_DIFF = "reconcile_diff"

# Technical fields that change on every recalculation or re-sync (PRP §8.1): never hashed.
HASH_EXCLUDED_FIELDS = frozenset(
    {
        "id",
        "calc_version",
        "created_at",
        "updated_at",
        "content_hash",
        "source_flow_id",
        "source_run_ids",
        "source_sync_batch_id",
        "frozen_at",
        "frozen_by",
        "version",
    }
)


def _month(value: date) -> str:
    return value.strftime("%Y-%m")


def order_line_key(
    store_id: str, report_key: str, order_no: str, order_item_no: str, gtin: str | None
) -> str:
    return "|".join((store_id, report_key, order_no, order_item_no, gtin or ""))


def unassigned_line_key(store_id: str, bill_month: date, source_kind: str, source_ref: str) -> str:
    return "|".join((store_id, _month(bill_month), source_kind, source_ref))


def reconcile_line_key(store_id: str, bill_month: date) -> str:
    return "|".join((store_id, _month(bill_month), RECONCILE_DIFF))


def _canonical(value: object) -> object:
    if isinstance(value, Decimal):
        return format(q4(value), "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_canonical(v) for v in value]
    return value


def content_hash(fields: Mapping[str, object]) -> str:
    """sha256 over business fields only; flow-sourced rows pass the flow ``row_hash``."""
    payload = {k: v for k, v in fields.items() if k not in HASH_EXCLUDED_FIELDS}
    text = json.dumps(_canonical(payload), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def set_hash(row_hashes: Iterable[str]) -> str:
    """Order-independent hash of a whole (store, month) result."""
    return hashlib.sha256("\n".join(sorted(row_hashes)).encode("ascii")).hexdigest()
