"""Read-only lookups the 8088 board joins in: Walmart Item ID by (store, MSKU) and product
owners by SKU. Both come from tables other modules already publish; a missing table gives
empty results (the column shows "—"), never an error and never an external call.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.orm import Session

LISTING_TABLE = "dim_walmart_listings"
IDENTITY_TABLE = "dwd_lingxing_sku_identity_index"
INFO_TABLE = "dwd_lingxing_sku_product_info_current"
_SPLIT = re.compile(r"[|,，、]")


def _has(session: Session, *tables: str) -> bool:
    inspector = inspect(session.connection())
    return all(inspector.has_table(name) for name in tables)


def item_ids_by_store_msku(
    session: Session, accounts: Iterable[str], pairs: set[tuple[str, str]]
) -> dict[tuple[str, str], str]:
    """``(store_id, msku) → item_id`` from the Lingxing Walmart listing dimension."""

    if not pairs or not _has(session, LISTING_TABLE):
        return {}
    stores = sorted({store for store, _ in pairs})
    mskus = sorted({msku for _, msku in pairs})
    rows = session.execute(
        text(
            f"select store_id, msku, item_id from {LISTING_TABLE} "
            "where source_account_ref in :accounts and store_id in :stores "
            "and msku in :mskus and item_id <> '' order by store_id, msku, item_id"
        ).bindparams(
            bindparam("accounts", expanding=True),
            bindparam("stores", expanding=True),
            bindparam("mskus", expanding=True),
        ),
        {"accounts": sorted(set(accounts)), "stores": stores, "mskus": mskus},
    ).all()
    found: dict[tuple[str, str], str] = {}
    for store_id, msku, item_id in rows:
        found.setdefault((store_id, msku), item_id)
    return found


def owners_by_sku(
    session: Session, accounts: Iterable[str], skus: set[str]
) -> dict[str, list[str]]:
    """``sku → owner names`` (8088: Lingxing product owner_names, several allowed)."""

    if not skus or not _has(session, IDENTITY_TABLE, INFO_TABLE):
        return {}
    rows = session.execute(
        text(
            "select i.lingxing_sku_code, p.owner_name "
            f"from {IDENTITY_TABLE} i "
            f"join {INFO_TABLE} p on p.identity_id = i.id "
            "and p.lingxing_sku_id = i.lingxing_sku_id "
            "and p.provider = i.provider "
            "and p.source_account_ref = i.source_account_ref "
            "where i.is_active and i.source_account_ref in :accounts "
            "and i.lingxing_sku_code in :skus"
        ).bindparams(bindparam("accounts", expanding=True), bindparam("skus", expanding=True)),
        {"accounts": sorted(set(accounts)), "skus": sorted(skus)},
    ).all()
    found: dict[str, set[str]] = {}
    for sku, names in rows:
        for name in _SPLIT.split(names or ""):
            if name.strip():
                found.setdefault(sku, set()).add(name.strip())
    return {sku: sorted(names) for sku, names in found.items()}
