"""The one ItemID attribution rule shared by the purchase board and the domestic boards.

Owner decision 2026-10-31: the rule used to be written twice (``pmc_purchase.refresh``
for the DWS board, ``pmc_domestic.board_item_ids`` for the inbound board and packing
candidates) and the two copies drifted. Both now call ``resolve_item_identities``; they
differ only in how they gather the inputs (which remark texts belong to the row, which
listings are candidates) and in where the result is stored.

Rule (handover: docs/sop/pmc/purchase-board.md, docs/sop/domestic-inbound-board-m1.md):

1. Remark ItemIDs (every standalone 11-digit token, ``ITEMID:`` first) are trusted when a
   listing of the row's **store** carries that item id, whatever the listing's local SKU
   says. A local SKU that is present and differs from the row SKU is flagged
   ``sku_mismatch``; it is never a reason to drop the id. Every verified id is kept.
2. Without verified remark ids: every store listing whose local SKU equals the row SKU,
   or, when there is none, every store listing with a blank local SKU whose MSKU equals one
   of the row's purchase-line MSKUs. Several ids are all kept (the callers show them as
   "multiple" and never pick one silently).
3. Without a store (``store_id`` blank) nothing is attributed here; callers that allow a
   single-store SKU to decide the store do that themselves.

This module has no database or framework imports.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from app.modules.pmc_purchase.remark_item_ids import extract_remark_item_ids

RULE_VERSION = "purchase.remark.store.v2"

type IdentitySource = Literal["remark", "listing"]


@dataclass(frozen=True, slots=True)
class ListingCandidate:
    store_id: str
    item_id: str
    local_sku: str | None = None
    gtin: str | None = None
    msku: str | None = None
    fulfillment_type: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    item_id: str
    source: IdentitySource
    gtin: str | None
    msku: str | None
    local_sku: str | None
    fulfillment_type: str | None
    sku_mismatch: bool


@dataclass(frozen=True, slots=True)
class Resolution:
    identities: tuple[ResolvedIdentity, ...]
    # Remark ids that no listing of the store carries (kept as evidence only).
    unverified_remark_ids: tuple[str, ...]

    @property
    def source(self) -> IdentitySource | None:
        return self.identities[0].source if self.identities else None

    @property
    def item_ids(self) -> list[str]:
        return [identity.item_id for identity in self.identities]

    @property
    def sku_mismatch_ids(self) -> list[str]:
        return [identity.item_id for identity in self.identities if identity.sku_mismatch]


def _clean(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _store_matches(listings: Sequence[ListingCandidate], predicate) -> list[ListingCandidate]:
    matches: dict[str, ListingCandidate] = {}
    for listing in listings:
        if predicate(listing):
            matches.setdefault(_clean(listing.item_id), listing)
    return list(matches.values())


def resolve_item_identities(
    *,
    store_id: str | None,
    sku: str | None,
    remark_texts: Sequence[str | None],
    line_mskus: Iterable[str | None] = (),
    listings: Sequence[ListingCandidate],
) -> Resolution:
    """Apply the shared rule for one row (see module docstring)."""

    store = _clean(store_id)
    row_sku = _clean(sku)
    remark_ids = extract_remark_item_ids(remark_texts)
    if not store:
        return Resolution(identities=(), unverified_remark_ids=tuple(remark_ids))
    store_listings = [item for item in listings if _clean(item.store_id) == store]
    by_item: dict[str, ListingCandidate] = {}
    for item in store_listings:
        by_item.setdefault(_clean(item.item_id), item)

    def identity(listing: ListingCandidate, source: IdentitySource) -> ResolvedIdentity:
        local = _clean(listing.local_sku)
        return ResolvedIdentity(
            item_id=_clean(listing.item_id),
            source=source,
            gtin=listing.gtin,
            msku=listing.msku,
            local_sku=listing.local_sku,
            fulfillment_type=listing.fulfillment_type,
            sku_mismatch=bool(local) and bool(row_sku) and local != row_sku,
        )

    verified = [item_id for item_id in remark_ids if item_id in by_item]
    unverified = tuple(item_id for item_id in remark_ids if item_id not in by_item)
    if verified:
        return Resolution(
            identities=tuple(identity(by_item[item_id], "remark") for item_id in verified),
            unverified_remark_ids=unverified,
        )
    fallback: list[ListingCandidate] = []
    if row_sku:
        fallback = _store_matches(store_listings, lambda item: _clean(item.local_sku) == row_sku)
    if not fallback:
        mskus = {_clean(value) for value in line_mskus if _clean(value)}
        if mskus:
            fallback = _store_matches(
                store_listings,
                lambda item: not _clean(item.local_sku) and _clean(item.msku) in mskus,
            )
    return Resolution(
        identities=tuple(identity(item, "listing") for item in fallback),
        unverified_remark_ids=unverified,
    )
