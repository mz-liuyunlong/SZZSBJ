"""Deterministic customs policy from Lingxing purchase orders; materialized at publication."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

RULE = "domestic.customs.v2"
ONLINE_BANK_TRANSFER_METHOD = 1


def _int_flag(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _payment_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(value.split())


def payment_is_online_bank_transfer(
    payment_method: object, payment: object = None
) -> bool:
    if _int_flag(payment_method) == ONLINE_BANK_TRANSFER_METHOD:
        return True
    text = _payment_text(payment)
    return "网银转账" in text if text else False


def is_tax_included(value: object) -> bool:
    return _int_flag(value) == 1


def purchase_order_requires_customs(header: Mapping[str, Any]) -> bool:
    return payment_is_online_bank_transfer(
        header.get("payment_method"), header.get("payment")
    ) or is_tax_included(header.get("is_tax"))


def _order_remark(order_sn: str, header: Mapping[str, Any]) -> str:
    if payment_is_online_bank_transfer(
        header.get("payment_method"), header.get("payment")
    ):
        method = header.get("payment")
        if isinstance(method, str) and method.strip():
            return f"{order_sn}：支付方式 {method.strip()}"
        return f"{order_sn}：支付方式网银转账"
    if is_tax_included(header.get("is_tax")):
        return f"{order_sn}：含税"
    return order_sn


def _order_field(header: Mapping[str, Any]) -> str:
    if payment_is_online_bank_transfer(
        header.get("payment_method"), header.get("payment")
    ):
        return "purchase_order.payment_method"
    if is_tax_included(header.get("is_tax")):
        return "purchase_order.is_tax"
    return "purchase_order.header"


def customs_proof(*, orders: Sequence[Mapping[str, Any]] = ()):
    """Derive default customs from linked purchase order headers (OR across orders)."""
    hits = [o for o in orders if purchase_order_requires_customs(o)]
    if hits:
        hit = hits[0]
        order_sn = str(hit.get("order_sn") or "")
        return {
            "value": True,
            "source": "purchase_order",
            "rule": RULE,
            "field": _order_field(hit),
            "remark": _order_remark(order_sn, hit)[:500],
            "ref": hit.get("ref"),
            "observed_at": hit.get("observed_at"),
        }
    if orders:
        hit = orders[0]
        order_sn = str(hit.get("order_sn") or "")
        return {
            "value": False,
            "source": "purchase_order",
            "rule": RULE,
            "field": "purchase_order.header",
            "remark": f"{order_sn}：非网银转账且不含税"[:500],
            "ref": hit.get("ref"),
            "observed_at": hit.get("observed_at"),
        }
    return {
        "value": False,
        "source": "default",
        "rule": RULE,
        "field": None,
        "remark": None,
        "ref": None,
        "observed_at": None,
    }


def candidate_customs(proof):
    """Publications without recognized proof stay explicit defaults until republished."""
    missing = {
        "customs_default": False,
        "customs_default_src": "default",
        "customs_proof": None,
    }
    if not isinstance(proof, dict) or not isinstance(proof.get("value"), bool):
        return missing
    rule = proof.get("rule")
    source = proof.get("source")
    if rule == RULE and source == "purchase_order":
        return {
            "customs_default": proof["value"],
            "customs_default_src": "purchase_order",
            "customs_proof": proof,
        }
    if rule == "domestic.customs.v1" and source in (
        "default",
        "product_remark",
        "purchase_remark",
    ):
        return {
            "customs_default": proof["value"],
            "customs_default_src": proof["source"],
            "customs_proof": proof,
        }
    return missing
