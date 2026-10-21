"""Customs defaults are source-derived; explicit human choices remain distinct."""

import pytest
import test_packing_approval as m1
from app.modules.pmc_domestic.packing_customs_rules import customs_proof, remark_flag
from app.modules.pmc_domestic.packing_schemas import PackingQuery
from app.modules.pmc_domestic.packing_service import PackingService

db = m1.db
seeded = m1.seeded


def evidence(note, time="2026-10-20", ref="fixture"):
    return {"remark": note, "time": time, "ref": ref, "field": "fixture.remark"}


@pytest.mark.parametrize(
    "note,result",
    [
        ("报关", True),
        ("采购报关", True),
        ("不报关", False),
        ("免报关", False),
        ("无需报关", False),
        ("不需要报关", False),
        ("不用报关", False),
        ("不 报关", False),
        ("已分配采购", None),
        (None, None),
    ],
)
def test_remark_negation_precedes_positive(note, result):
    assert remark_flag(note) is result


def test_product_priority_and_blank_field_does_not_invent_fallback():
    assert customs_proof(evidence("不报关"), [evidence("报关")])["value"] is False
    assert (
        customs_proof(evidence("报关"), [evidence("不报关")])["source"]
        == "product_remark"
    )
    assert customs_proof(evidence(""), [evidence("报关")])["source"] == "default"


def test_purchase_latest_negative_or_any_positive_and_empty_default():
    yes = evidence("报关", "1", "yes")
    no = evidence("不报关", "2", "no")
    neutral = evidence("已采购", "3", "neutral")
    assert customs_proof(None, [yes, no])["value"] is False
    assert customs_proof(None, [yes, neutral])["value"] is True
    assert customs_proof(None, [no, neutral])["source"] == "default"
    assert customs_proof()["value"] is False


@pytest.mark.parametrize(
    "choice,value,source",
    [
        ("default", True, "product_remark"),
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
        "customs_proof": customs_proof(evidence("报关")),
    }
    db.flush()
    service = PackingService(db)
    scope = frozenset({account})
    row = service.pending(PackingQuery(), scope).items[0]
    assert row.customs_default is True
    cmd = m1.command(row, customs=choice)
    result = service.decide(row.id, cmd, "approve", "fixture", scope)
    assert result.customs_value is value and result.customs_src == source
    assert result.snapshot.customs_proof["remark"] == "报关"


def test_customs_source_change_invalidates_approval(db, seeded):
    from app.core.api import ApiError

    account, board, _ = seeded
    service = PackingService(db)
    scope = frozenset({account})
    row = service.pending(PackingQuery(), scope).items[0]
    board.payload_json = {
        **board.payload_json,
        "customs_proof": customs_proof(evidence("报关")),
    }
    db.flush()
    with pytest.raises(ApiError) as error:
        service.decide(row.id, m1.command(row), "approve", "fixture", scope)
    assert error.value.status_code == 409
