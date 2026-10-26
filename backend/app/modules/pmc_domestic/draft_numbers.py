"""Draft numbers already shown on the purchase board, keyed by account, PO, and SKU."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.modules.pmc_purchase.gate3_models import DwsPurchaseBoard


class DraftRow(Protocol):
    source_account_ref: str
    sku: str
    purchase_order_sns: list[str]
    draft_nos: list[str]


def attach_draft_numbers(session: Session, rows: Sequence[DraftRow], accounts: frozenset[str]) -> None:
    """Fill ``draft_nos`` from ``dws_purchase_board.draft_no`` (采购备注 ``草稿:CG…``)."""

    pairs: set[tuple[str, str, str]] = set()
    for row in rows:
        if row.source_account_ref not in accounts or not row.sku:
            continue
        for sn in row.purchase_order_sns or []:
            if sn:
                pairs.add((row.source_account_ref, sn, row.sku))
    lookup = _load(session, pairs)
    for row in rows:
        seen: list[str] = []
        for sn in row.purchase_order_sns or []:
            for draft in lookup.get((row.source_account_ref, sn, row.sku), ()):
                if draft not in seen:
                    seen.append(draft)
        row.draft_nos = seen


def _load(session: Session, pairs: set[tuple[str, str, str]]) -> dict[tuple[str, str, str], list[str]]:
    if not pairs or not inspect(session.get_bind()).has_table(DwsPurchaseBoard.__tablename__):
        return {}
    accounts = {account for account, _, _ in pairs}
    order_sns = {sn for _, sn, _ in pairs}
    skus = {sku for _, _, sku in pairs}
    found = session.execute(
        select(
            DwsPurchaseBoard.source_account_ref,
            DwsPurchaseBoard.order_sn,
            DwsPurchaseBoard.sku,
            DwsPurchaseBoard.draft_no,
        ).where(
            DwsPurchaseBoard.source_account_ref.in_(accounts),
            DwsPurchaseBoard.order_sn.in_(order_sns),
            DwsPurchaseBoard.sku.in_(skus),
            DwsPurchaseBoard.draft_no.is_not(None),
            DwsPurchaseBoard.draft_no != "",
        )
    ).all()
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for account, order_sn, sku, draft_no in found:
        key = (account, order_sn, sku)
        if key not in pairs or not draft_no:
            continue
        bucket = grouped.setdefault(key, [])
        if draft_no not in bucket:
            bucket.append(draft_no)
    for bucket in grouped.values():
        bucket.sort()
    return grouped
