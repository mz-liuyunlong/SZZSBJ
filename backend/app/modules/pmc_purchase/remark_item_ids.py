"""Shared ItemID remark parsing for the purchase board and domestic inbound board."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.modules.pmc_purchase.calculations import (
    BARE_ITEMID_PATTERN,
    ItemIdAttribution,
)
from app.modules.pmc_purchase.models import (
    LingxingPurchaseOrderItemOds,
    LingxingPurchasePlanOds,
)

PLAN_REMARK_KEYS: tuple[str, ...] = ("remark", "plan_remark", "item_purchase_remark")
LINE_REMARK_KEYS: tuple[str, ...] = ("remark", "item_purchase_remark")


def extract_remark_item_ids(texts: Sequence[str | None]) -> list[str]:
    """Every standalone 11-digit ItemID.

    Keep source-text encounter order as in the legacy purchase builder.
    A 14-digit GTIN does not count.
    """

    blobs = [text for text in texts if isinstance(text, str) and text.strip()]
    seen: list[str] = []
    for blob in blobs:
        for match in BARE_ITEMID_PATTERN.finditer(blob):
            _append_unique(seen, match.group(1))
    return seen


def item_ids_plan_then_line(
    plan_texts: Sequence[str | None],
    line_texts: Sequence[str | None],
) -> list[str]:
    """Merge source remarks in legacy line-first order (name retained for callers)."""
    return extract_remark_item_ids([*line_texts, *plan_texts])


def validated_remark_item_ids(
    plan_texts: Sequence[str | None],
    line_texts: Sequence[str | None],
    listing_item_ids: Sequence[str],
) -> list[str]:
    """Legacy purchase semantics: merge both remarks, keep all SKU-verified identities.

    Stable line-first order follows the source document. Multiple valid identities
    do not split quantities and are not an attribution error.
    """
    allowed = set(listing_item_ids)
    return [
        value for value in extract_remark_item_ids([*line_texts, *plan_texts]) if value in allowed
    ]


def resolve_purchase_board_item_id(
    *,
    plan_texts: Sequence[str | None],
    line_texts: Sequence[str | None],
    listing_item_id: str | None,
    packing_slip_item_id: str | None,
    packing_slip_pending: bool,
) -> ItemIdAttribution:
    """Scalar compatibility helper; the refresher persists verified multi-values separately.

    This scalar return must never select the first of several remark identities.
    """

    ids = item_ids_plan_then_line(plan_texts, line_texts)
    if len(ids) > 1:
        return ItemIdAttribution(None, "unresolved")
    if len(ids) == 1:
        return ItemIdAttribution(ids[0], "from_plan_remark")
    if _nonblank(listing_item_id):
        return ItemIdAttribution(str(listing_item_id).strip(), "from_listing")
    if _nonblank(packing_slip_item_id):
        return ItemIdAttribution(str(packing_slip_item_id).strip(), "from_packing_slip")
    if packing_slip_pending:
        return ItemIdAttribution(None, "pending_packing_slip")
    return ItemIdAttribution(None, "unresolved")


@dataclass(frozen=True, slots=True)
class OdsRemarkTexts:
    plan_by_sn: Mapping[str, tuple[str | None, ...]]
    line_by_key: Mapping[tuple[str, str], tuple[str | None, ...]]
    # Purchase line MSKU (``payload.msku``) by (order_sn, order_item_id): used to find the
    # listing when its local SKU is blank (owner decision 2026-10-31, rule 2).
    line_msku_by_key: Mapping[tuple[str, str], str] = field(default_factory=dict)


def load_ods_remark_texts(session: Session, account: str) -> OdsRemarkTexts | None:
    """Latest ODS remark texts for one account, or ``None`` when ODS tables are absent."""

    # Reuse the transaction connection: an engine-level inspector can roll back
    # pending writes when a single-connection pool returns the same connection.
    inspector = inspect(session.connection())
    if not inspector.has_table(LingxingPurchasePlanOds.__tablename__):
        return None
    if not inspector.has_table(LingxingPurchaseOrderItemOds.__tablename__):
        return None

    plan_by_sn = _latest_plan_texts(session, account)
    line_by_key, line_msku_by_key = _latest_line_texts(session, account)
    return OdsRemarkTexts(
        plan_by_sn=plan_by_sn, line_by_key=line_by_key, line_msku_by_key=line_msku_by_key
    )


def line_msku_for(ods: OdsRemarkTexts | None, line: object) -> str | None:
    if ods is None:
        return None
    key = (str(line.order_sn), str(line.order_item_id))
    value = ods.line_msku_by_key.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def plan_texts_for(
    ods: OdsRemarkTexts | None,
    plan: object | None,
    *,
    fallback_remark: str | None = None,
) -> list[str | None]:
    if ods is not None and plan is not None and (plan_sn := getattr(plan, "plan_sn", None)):
        texts = ods.plan_by_sn.get(str(plan_sn))
        if texts:
            return list(texts)
    if fallback_remark:
        return [fallback_remark]
    return []


def line_texts_for(
    ods: OdsRemarkTexts | None,
    line: object,
    *,
    fallback_item_id: str | None = None,
) -> list[str | None]:
    if ods is not None:
        key = (str(line.order_sn), str(line.order_item_id))
        texts = ods.line_by_key.get(key)
        if texts:
            return list(texts)
    if fallback_item_id and str(fallback_item_id).strip():
        token = str(fallback_item_id).strip()
        return [f"ITEMID:{token}" if token.isdigit() else token]
    return []


def remark_ids_conflict(ids: Sequence[str]) -> bool:
    return len(ids) > 1


def single_remark_item_id(
    plan_texts: Sequence[str | None],
    line_texts: Sequence[str | None],
) -> str | None:
    """One stored ItemID for DWD when remark attribution is unambiguous."""

    ids = item_ids_plan_then_line(plan_texts, line_texts)
    return ids[0] if len(ids) == 1 else None


def line_texts_from_ods_item(item: object) -> list[str | None]:
    payload = _payload(getattr(item, "payload_json", None))
    remark = getattr(item, "remark", None)
    purchase_remark = _payload_text(payload, "item_purchase_remark")
    return [remark if isinstance(remark, str) else None, purchase_remark]


def plan_texts_from_ods_plan(plan: object) -> list[str | None]:
    payload = _payload(getattr(plan, "payload_json", None))
    return [
        getattr(plan, "remark", None) if isinstance(getattr(plan, "remark", None), str) else None,
        getattr(plan, "plan_remark", None)
        if isinstance(getattr(plan, "plan_remark", None), str)
        else None,
        _payload_text(payload, "item_purchase_remark"),
    ]


def _latest_plan_texts(session: Session, account: str) -> dict[str, tuple[str | None, ...]]:
    rows = session.scalars(
        select(LingxingPurchasePlanOds).where(LingxingPurchasePlanOds.source_account_ref == account)
    )
    latest: dict[str, tuple[object, LingxingPurchasePlanOds]] = {}
    for row in rows:
        payload = _payload(row.payload_json)
        version = _version(payload, row.observed_at, row.id)
        key = row.plan_sn
        current = latest.get(key)
        if current is None or version > current[0]:
            latest[key] = (version, row)
    out: dict[str, tuple[str | None, ...]] = {}
    for plan_sn, (_, row) in latest.items():
        payload = _payload(row.payload_json)
        out[plan_sn] = (
            row.remark,
            row.plan_remark,
            _payload_text(payload, "item_purchase_remark"),
        )
    return out


def _latest_line_texts(
    session: Session, account: str
) -> tuple[dict[tuple[str, str], tuple[str | None, ...]], dict[tuple[str, str], str]]:
    rows = session.scalars(
        select(LingxingPurchaseOrderItemOds).where(
            LingxingPurchaseOrderItemOds.source_account_ref == account
        )
    )
    latest: dict[tuple[str, str], tuple[object, LingxingPurchaseOrderItemOds]] = {}
    for row in rows:
        if row.is_delete in (1, "1"):
            continue
        payload = _payload(row.payload_json)
        version = _version(payload, row.observed_at, row.id)
        key = (row.order_sn, str(row.item_id))
        current = latest.get(key)
        if current is None or version > current[0]:
            latest[key] = (version, row)
    out: dict[tuple[str, str], tuple[str | None, ...]] = {}
    mskus: dict[tuple[str, str], str] = {}
    for key, (_, row) in latest.items():
        payload = _payload(row.payload_json)
        out[key] = (row.remark, _payload_text(payload, "item_purchase_remark"))
        msku = _payload_text(payload, "msku")
        if msku:
            mskus[key] = msku.strip()
    return out, mskus


def _payload(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _payload_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _version(
    payload: dict[str, object], observed_at: object, row_id: object
) -> tuple[str, str, str]:
    update = payload.get("update_time")
    if isinstance(update, str) and update.strip():
        return ("1", update, str(row_id))
    if observed_at is not None:
        return ("2", str(observed_at), str(row_id))
    return ("3", "", str(row_id))


def _append_unique(seen: list[str], item_id: str) -> None:
    if item_id not in seen:
        seen.append(item_id)


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
