"""Advisory quantities only; approval still reserves the operator's confirmed quantity."""

from fractions import Fraction


def batch_metrics(batches, inbound_sn, arrival_status, history_complete):
    """Observed batches; a negative assertion requires complete published history."""
    ordered = sorted(batches, key=lambda sn: (str(batches[sn] or "9999"), sn))
    count = len(batches) or None
    split = (
        True
        if count and count > 1
        else (False if count == 1 and arrival_status == "full" and history_complete else None)
    )
    return {
        "split_arrival": split,
        "arrival_batch_count": count,
        "arrival_batch_index": ordered.index(inbound_sn) + 1
        if inbound_sn in ordered and all(batches.values())
        else None,
    }


def arrival_metrics(
    purchased: int | None, received: list[int | None], outstanding: list[int | None]
) -> dict:
    # Lingxing quantity_entry is received; quantity_receive is outstanding.
    # Sum both source counters independently: missing evidence must not be inferred.
    total = sum(received) if received and all(type(v) is int and v >= 0 for v in received) else None
    pending = (
        sum(outstanding)
        if outstanding and all(type(v) is int and v >= 0 for v in outstanding)
        else None
    )
    status = "unknown"
    if purchased is not None and total is not None and pending is not None:
        if pending == 0 and total >= purchased:
            status = "full"
        elif pending > 0 and total < purchased:
            status = "partial" if total > 0 else "none"
    return {"arrival_received": total, "arrival_pending": pending, "arrival_status": status}


def suggest_quantities(total, available, weights, consumed, box_pcs):
    """Largest remainders in whole boxes; do not redistribute an approved identity's share.

    Incomplete weights return no suggestion. A remainder smaller than one box stays
    explicit for human review, rather than silently overallocating another identity.
    """
    if total is None or available is None or not weights or any(v <= 0 for v in weights.values()):
        return {}, None
    unit = box_pcs or 1
    units, tail = divmod(total, unit)
    denominator = sum(weights.values())
    exact = {key: Fraction(units) * value / denominator for key, value in weights.items()}
    counts = {key: int(value) for key, value in exact.items()}
    left = units - sum(counts.values())
    for key in sorted(exact, key=lambda k: (-(exact[k] - counts[k]), k))[:left]:
        counts[key] += 1
    result = {}
    remaining = available
    for key in sorted(counts):
        target = max(0, counts[key] * unit - consumed.get(key, 0))
        # A partially consumed allocation cannot create a new partial-box suggestion.
        quantity = min(target // unit * unit, remaining // unit * unit)
        result[key] = quantity
        remaining -= quantity
    return result, tail
