"""Account-scoped Walmart store discovery for WFS settlement collection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class WfsStoreDiscoveryError(ValueError):
    """Safe discovery failure without store or account identifiers."""


@dataclass(frozen=True, slots=True)
class WfsSettlementStore:
    source_account_ref: str
    store_id: str
    store_name: str
    sid: str


def _identifier(value: object) -> str:
    if value is None or isinstance(value, (bool, float)):
        return ""
    return str(value).strip()


def validate_walmart_stores(
    records: list[dict[str, Any]],
    *,
    source_account_ref: str,
) -> tuple[WfsSettlementStore, ...]:
    """Fail closed on missing, ambiguous or cross-account store identities."""

    if not source_account_ref or source_account_ref != source_account_ref.strip():
        raise WfsStoreDiscoveryError("WFS_INVALID_ACCOUNT_SCOPE")

    result: list[WfsSettlementStore] = []
    seen_stores: set[str] = set()
    seen_names: set[str] = set()

    for record in records:
        if _identifier(record.get("source_account_ref")) != source_account_ref:
            raise WfsStoreDiscoveryError("WFS_CROSS_ACCOUNT_STORE")

        store_id = _identifier(record.get("store_id"))
        sid = _identifier(record.get("sid"))
        store_name = _identifier(record.get("store_name"))

        if not store_id:
            raise WfsStoreDiscoveryError("WFS_STORE_ID_MISSING")
        if not store_name:
            raise WfsStoreDiscoveryError("WFS_STORE_NAME_MISSING")

        normalized_name = store_name.casefold()

        if store_id in seen_stores:
            raise WfsStoreDiscoveryError("WFS_DUPLICATE_STORE_ID")
        if normalized_name in seen_names:
            raise WfsStoreDiscoveryError("WFS_AMBIGUOUS_STORE_NAME")

        seen_stores.add(store_id)
        seen_names.add(normalized_name)

        result.append(
            WfsSettlementStore(
                source_account_ref=source_account_ref,
                store_id=store_id,
                store_name=store_name,
                sid=sid,
            )
        )

    if not result:
        raise WfsStoreDiscoveryError("WFS_NO_WALMART_STORES")

    return tuple(sorted(result, key=lambda item: item.store_id))


def discover_walmart_stores(
    session: Session,
    *,
    source_account_ref: str,
) -> tuple[WfsSettlementStore, ...]:
    """Read Walmart store dimension only; never sync or mutate provider data."""

    if not source_account_ref or source_account_ref != source_account_ref.strip():
        raise WfsStoreDiscoveryError("WFS_INVALID_ACCOUNT_SCOPE")

    rows = (
        session.execute(
            text(
                "select source_account_ref,store_id,store_name,sid "
                "from dim_lingxing_stores "
                "where source_account_ref=:account "
                "and (platform_code='walmart' or platform_code_raw='10008') "
                "order by store_id"
            ),
            {"account": source_account_ref},
        )
        .mappings()
        .all()
    )

    return validate_walmart_stores(
        [dict(row) for row in rows],
        source_account_ref=source_account_ref,
    )


def settlement_store_scope(
    stores: tuple[WfsSettlementStore, ...],
) -> tuple[dict[str, object], ...]:
    """Build one strictly scoped provider request seed per store."""

    return tuple({"sids": store.store_id, "store_id": store.store_id} for store in stores)
