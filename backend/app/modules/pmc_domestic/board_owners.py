"""Current product owner for an inbound row, keyed by account and SKU."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.orm import Session

from app.modules.pmc_domestic.inbound_schemas import ProductOwner

IDENTITY_TABLE = "dwd_lingxing_sku_identity_index"
INFO_TABLE = "dwd_lingxing_sku_product_info_current"


class OwnerRow(Protocol):
    source_account_ref: str
    sku: str
    owner: ProductOwner


def classify_owner(rows: Sequence[tuple[str, str | None, str | None]]) -> ProductOwner:
    """One active identity and one owner UID resolve. Several identities or UIDs conflict."""

    identities = {identity for identity, _, _ in rows if identity}
    if not identities:
        return ProductOwner()
    if len(identities) != 1:
        return ProductOwner(status="conflict")
    uids = sorted({uid.strip() for _, uid, _ in rows if isinstance(uid, str) and uid.strip()})
    if len(uids) != 1:
        return ProductOwner(status="conflict" if uids else "missing")
    uid = uids[0]
    names = [
        name.strip()
        for _, owner_uid, name in rows
        if isinstance(owner_uid, str)
        and owner_uid.strip() == uid
        and isinstance(name, str)
        and name.strip()
    ]
    return ProductOwner(uid=uid, name=names[0] if names else None, status="resolved")


def attach_board_owners(
    session: Session, rows: Sequence[OwnerRow], accounts: frozenset[str]
) -> None:
    """Fill the current product owner. A missing table leaves every row unknown."""

    pairs = {
        (row.source_account_ref, row.sku)
        for row in rows
        if row.source_account_ref in accounts and row.sku
    }
    found = _load(session, pairs)
    for row in rows:
        row.owner = found.get((row.source_account_ref, row.sku), ProductOwner())


def _load(session: Session, pairs: set[tuple[str, str]]) -> dict[tuple[str, str], ProductOwner]:
    if not pairs:
        return {}
    inspector = inspect(session.get_bind())
    if not inspector.has_table(IDENTITY_TABLE) or not inspector.has_table(INFO_TABLE):
        return {}
    accounts = list({account for account, _ in pairs})
    skus = list({sku for _, sku in pairs})
    loaded = session.execute(
        text(
            "select i.source_account_ref, i.lingxing_sku_code, i.id, "
            "p.owner_uid, p.owner_name "
            f"from {IDENTITY_TABLE} i "
            f"left join {INFO_TABLE} p on p.identity_id = i.id "
            "and p.lingxing_sku_id = i.lingxing_sku_id "
            "and p.provider = i.provider "
            "and p.source_account_ref = i.source_account_ref "
            "where i.is_active "
            "and i.source_account_ref in :accounts "
            "and i.lingxing_sku_code in :skus"
        ).bindparams(bindparam("accounts", expanding=True), bindparam("skus", expanding=True)),
        {"accounts": accounts, "skus": skus},
    ).all()
    grouped: dict[tuple[str, str], list[tuple[str, str | None, str | None]]] = {}
    for row in loaded:
        key = (row.source_account_ref, row.lingxing_sku_code)
        if key not in pairs:
            continue
        grouped.setdefault(key, []).append((str(row.id), row.owner_uid, row.owner_name))
    return {key: classify_owner(items) for key, items in grouped.items()}
