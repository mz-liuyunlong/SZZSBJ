"""Business dictionaries and small rules (PRP §0.4, §8.6, §8.7)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from .inputs import ReviewAcceleratorInput
from .money import ZERO, allocate

# §0.4 Lingxing businessType → category.  Unknown types → "unknown" (alert, not calculated).
BUSINESS_TYPE_CATEGORY: Mapping[str, str] = {
    "LIQ": "loss",
    "ODB": "loss",
    "RFS": "non_loss",
    "MTR": "non_loss",
    "ADJ": "claim",
    "CCA": "claim",
    "D16": "claim",
    "ADX": "claim",
    "VTM": "claim",
    "VDG": "unclassified",
    "NEGATIVE_INVENTORY": "lx_adjust",
}
ALERT_CATEGORIES = frozenset({"unclassified", "unknown", "lx_adjust"})

# Fee detail types that are disposal operation fees: moved once from WFS service fee to
# the 弃置损耗 column (§0.4 / §8.8).  Everything else in the fee detail weights WFS service.
DISPOSAL_FEE_TYPES = frozenset({"RC_InventoryDisposalFee", "WFS_DisposalOrderFee"})


def inventory_category(business_type: str) -> str:
    return BUSINESS_TYPE_CATEGORY.get(business_type.strip().upper(), "unknown")


def review_unit_price(price: Decimal) -> Decimal:
    """单价 = clamp(5 + 0.25 × 售价, 10, 30) USD (§8.6)."""
    return min(max(Decimal("5") + Decimal("0.25") * price, Decimal("10")), Decimal("30"))


@dataclass(frozen=True)
class ReviewWeights:
    weights: dict[str, Decimal] | None
    mode: str  # delta_price / sales_first_period / sales_zero_delta
    unassigned_reason: str | None = None  # snapshot_missing / no_sales / price_missing


def review_accelerator_weights(
    inp: ReviewAcceleratorInput | None, sales_by_item: Mapping[str, Decimal]
) -> ReviewWeights:
    """§8.6. No fallback branch beyond the two sales rules Rocky kept.

    A missing price for an item with new reviews sends the whole fee to 待指定
    (reason price_missing): no average price, no minimum price, no switch to sales.
    """
    if inp is None or inp.current is None:
        return ReviewWeights(None, "none", "snapshot_missing")
    enrolled = [s.item_id for s in inp.current]

    def by_sales(mode: str) -> ReviewWeights:
        weights = {i: max(sales_by_item.get(i, ZERO), ZERO) for i in enrolled}
        if not weights or sum(weights.values(), ZERO) == 0:
            return ReviewWeights(None, mode, "no_sales")
        return ReviewWeights(weights, mode)

    if inp.previous is None:
        return by_sales("sales_first_period")
    prev = {s.item_id: s.reviews_collected for s in inp.previous}
    delta = {s.item_id: max(s.reviews_collected - prev.get(s.item_id, 0), 0) for s in inp.current}
    if all(d == 0 for d in delta.values()):
        return by_sales("sales_zero_delta")
    weights: dict[str, Decimal] = {}
    for item_id, d in delta.items():
        if d == 0:
            weights[item_id] = ZERO
            continue
        price = inp.price_by_item.get(item_id)
        if price is None:
            return ReviewWeights(None, "delta_price", "price_missing")
        weights[item_id] = Decimal(d) * review_unit_price(price)
    return ReviewWeights(weights, "delta_price")


@dataclass(frozen=True)
class OwnerItem:
    key: tuple[str, str]  # (store_id, item_id)
    owner_ref: str | None
    sales_usd: Decimal
    sales_quantity: Decimal


@dataclass(frozen=True)
class NetProfitResult:
    share_by_item: dict[tuple[str, str], Decimal] | None  # CNY; None = not published
    share_by_owner: dict[str, Decimal]
    owners_in_n: list[str]
    blockers: list[str]


def allocate_net_profit(
    items: list[OwnerItem],
    company_cost_cny: Decimal | None,
    fixed_cny: Decimal,
    excluded_owner_ids: list[str],
) -> NetProfitResult:
    """§8.7: C − fixed × N split by owner sales share; each owner's part by item sales."""
    blockers: list[str] = []
    if any(i.owner_ref is None and i.sales_quantity > 0 for i in items):
        blockers.append("OWNER_MISSING")
    excluded = set(excluded_owner_ids)
    owner_sales: dict[str, Decimal] = {}
    for i in items:
        if i.owner_ref is None or i.owner_ref in excluded or i.sales_quantity <= 0:
            continue
        owner_sales[i.owner_ref] = owner_sales.get(i.owner_ref, ZERO) + i.sales_usd
    owners = sorted(owner_sales)
    if any(owner_sales[o] <= 0 for o in owners):
        blockers.append("OWNER_SALES_ZERO")
    if company_cost_cny is None or blockers or not owners:
        return NetProfitResult(None, {}, owners, blockers)
    remainder = company_cost_cny - fixed_cny * len(owners)
    rest = allocate(remainder, {o: owner_sales[o] for o in owners})
    share_by_owner = {o: fixed_cny + rest[o] for o in owners}
    share_by_item: dict[tuple[str, str], Decimal] = {i.key: ZERO for i in items}
    for o in owners:
        mine = {
            i.key: max(i.sales_usd, ZERO)
            for i in items
            if i.owner_ref == o and i.sales_quantity > 0
        }
        share_by_item.update(allocate(share_by_owner[o], mine))
    return NetProfitResult(share_by_item, share_by_owner, owners, blockers)
