"""Pure completion decision; stock availability is supplied by a locked repository read.

None means unavailable/unconfirmed evidence, never zero stock. This function does
not query providers, mutate allocations or send notifications.
"""

from dataclasses import dataclass

UNDER_REASONS = {
    "shortage": "实物短少",
    "damage": "破损",
    "box_capacity": "装不下箱",
    "other": "其他",
}


@dataclass(frozen=True)
class CompletionDecision:
    outcome: str
    unpacked_qty: int = 0
    excess_qty: int = 0
    gap_qty: int | None = None
    blocker: str | None = None


def decide_completion(
    approved,
    packed,
    *,
    extra_available=None,
    reason_category=None,
    reason=None,
    confirm_extra=False,
):
    if (
        isinstance(approved, bool)
        or isinstance(packed, bool)
        or not isinstance(approved, int)
        or not isinstance(packed, int)
        or min(approved, packed) <= 0
    ):
        raise ValueError("positive integer quantities required")
    if extra_available is not None and (
        isinstance(extra_available, bool)
        or not isinstance(extra_available, int)
        or extra_available < 0
    ):
        raise ValueError("nonnegative extra availability required")
    if packed == approved:
        return CompletionDecision("complete")
    if packed < approved:
        missing = reason_category not in UNDER_REASONS or (
            reason_category == "other" and len((reason or "").strip()) < 2
        )
        return CompletionDecision(
            "blocked" if missing else "complete",
            unpacked_qty=approved - packed,
            blocker="UNDERPACK_REASON_REQUIRED" if missing else None,
        )
    excess = packed - approved
    if extra_available is None:
        return CompletionDecision(
            "blocked", excess_qty=excess, blocker="EXTRA_STOCK_RULE_UNCONFIRMED"
        )
    if excess <= extra_available:
        return CompletionDecision(
            "complete" if confirm_extra else "blocked",
            excess_qty=excess,
            blocker=None if confirm_extra else "EXTRA_STOCK_CONFIRM_REQUIRED",
        )
    if len((reason or "").strip()) < 2:
        return CompletionDecision(
            "blocked",
            excess_qty=excess,
            gap_qty=excess - extra_available,
            blocker="OVERPACK_REASON_REQUIRED",
        )
    return CompletionDecision(
        "supplement_required", excess_qty=excess, gap_qty=excess - extra_available
    )
