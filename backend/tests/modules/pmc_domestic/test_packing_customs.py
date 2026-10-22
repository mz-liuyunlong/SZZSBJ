"""Customs defaults follow purchase order payment/tax terms; manual choice stays distinct."""

import pytest
import test_packing_approval as m1
from app.modules.pmc_domestic.packing_customs_rules import (
    customs_proof,
    is_tax_included,
    payment_is_online_bank_transfer,
    purchase_order_requires_customs,
)
from app.modules.pmc_domestic.packing_schemas import PackingQuery
from app.modules.pmc_domestic.packing_service import PackingService

db = m1.db
seeded = m1.seeded


def order(**fields):
    base = {
        "order_sn": "PO1",
        "ref": "fixture",
        "observed_at": "2026-10-20",
        "payment_method": 2,
        "payment": "网上支付",
        "is_tax": 0,
    }
    base.update(fields)
    return base


@pytest.mark.parametrize(
    "method,payment,expected",
    [
        (1, "", True),
        (2, "网银转账", True),
        (2, "网上支付", False),
        (0, "网银转账", True),
    ],
)
def test_payment_online_bank_transfer(method, payment, expected):
    assert payment_is_online_bank_transfer(method, payment) is expected


@pytest.mark.parametrize("value,expected", [(1, True), (0, False), ("1", True), (None, False)])
def test_is_tax_included(value, expected):
    assert is_tax_included(value) is expected


def test_purchase_order_or_condition():
    assert purchase_order_requires_customs({"payment_method": 1, "is_tax": 0}) is True
    assert purchase_order_requires_customs({"payment_method": 2, "is_tax": 1}) is True
    assert purchase_order_requires_customs({"payment_method": 2, "is_tax": 0}) is False


def test_customs_proof_any_linked_order_triggers_declare():
    proof = customs_proof(
        orders=[order(is_tax=0), order(order_sn="PO2", payment_method=1, is_tax=0)]
    )
    assert proof["value"] is True and proof["source"] == "purchase_order"


def test_customs_proof_without_orders_defaults_false():
    assert customs_proof()["source"] == "default" and customs_proof()["value"] is False


def test_customs_proof_all_orders_non_matching():
    proof = customs_proof(orders=[order(), order(order_sn="PO2")])
    assert proof["value"] is False and proof["source"] == "purchase_order"


@pytest.mark.parametrize(
    "choice,value,source",
    [
        ("default", True, "purchase_order"),
        ("skip", False, "manual"),
        ("declare", True, "manual"),
    ],
)
def test_approval_uses_server_default_or_explicit_override(
    db, seeded, choice, value, source
):
    account, board, _ = seeded
    board.payload_json = {
        **board.payload_json,
        "customs_proof": customs_proof(orders=[order(payment_method=1)]),
    }
    db.flush()
    service = PackingService(db)
    scope = frozenset({account})
    row = service.pending(PackingQuery(), scope).items[0]
    assert row.customs_default is True
    cmd = m1.command(row, customs=choice)
    result = service.decide(row.id, cmd, "approve", "fixture", scope)
    assert result.customs_value is value and result.customs_src == source


def test_customs_source_change_invalidates_approval(db, seeded):
    from app.core.api import ApiError

    account, board, _ = seeded
    service = PackingService(db)
    scope = frozenset({account})
    row = service.pending(PackingQuery(), scope).items[0]
    board.payload_json = {
        **board.payload_json,
        "customs_proof": customs_proof(orders=[order(payment_method=1)]),
    }
    db.flush()
    with pytest.raises(ApiError) as error:
        service.decide(row.id, m1.command(row), "approve", "fixture", scope)
    assert error.value.status_code == 409
