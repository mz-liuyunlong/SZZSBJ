"""Deterministic legacy customs policy; materialized at publication, never during GET."""

RULE = "domestic.customs.v1"


def remark_flag(value):
    if not isinstance(value, str):
        return None
    value = "".join(value.split())
    if any(
        word in value
        for word in ("不报关", "免报关", "无需报关", "不需要报关", "不用报关")
    ):
        return False
    return True if "报关" in value else None


def customs_proof(product=None, purchases=()):
    """An existing blank product field is authoritative; fallback only if absent.

    Purchase fallback preserves the old latest-negative / any-positive policy.
    Evidence records contain a stable time, reference, source field and remark.
    """
    hit = product
    value = remark_flag(product["remark"]) if product is not None else None
    if product is None:
        rows = sorted(purchases, key=lambda r: (r["time"], r["ref"]))
        latest = rows[-1] if rows else None
        if latest and remark_flag(latest["remark"]) is False:
            value, hit = False, latest
        else:
            hit = next(
                (r for r in reversed(rows) if remark_flag(r["remark"]) is True), latest
            )
            value = remark_flag(hit["remark"]) if hit else None
            if value is False:
                value = None  # an older negative does not override a newer neutral note
    return {
        "value": value is True,
        "source": ("product_remark" if product is not None else "purchase_remark")
        if value is not None
        else "default",
        "rule": RULE,
        "field": hit.get("field") if hit else None,
        "remark": hit["remark"][:500] if hit else None,
        "ref": hit["ref"] if hit else None,
        "observed_at": hit.get("observed_at") if hit else None,
    }


def candidate_customs(proof):
    """Old publications have no proof; remain explicit defaults until republished."""
    if (
        not isinstance(proof, dict)
        or proof.get("rule") != RULE
        or not isinstance(proof.get("value"), bool)
    ):
        return {
            "customs_default": False,
            "customs_default_src": "default",
            "customs_proof": None,
        }
    if proof.get("source") not in ("default", "product_remark", "purchase_remark"):
        return {
            "customs_default": False,
            "customs_default_src": "default",
            "customs_proof": None,
        }
    return {
        "customs_default": proof["value"],
        "customs_default_src": proof["source"],
        "customs_proof": proof,
    }
