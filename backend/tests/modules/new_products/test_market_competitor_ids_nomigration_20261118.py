"""Competitor selection validation; existing JSONB, no schema change."""

import pytest
from pydantic import ValidationError

from app.modules.new_products.schemas import MarketWrite

BASE = {
    "source_account_ref": "account",
    "store_id": "store",
    "item_id": "20874953767",
    "score": 7,
    "reason": "Competition evidence verified by operator",
    "expected_version": 0,
    "risk_conditions": ["无"],
}


def payload(ids, none=False):
    return {**BASE, "competitor_ids": ids, "no_competitors": none}


def test_ids_required_unless_none():
    with pytest.raises(ValidationError):
        MarketWrite.model_validate(BASE)
    with pytest.raises(ValidationError):
        MarketWrite.model_validate(payload([]))
    data = payload(["20874953767", "00123456789"])
    obj = MarketWrite.model_validate(data)
    assert obj.competitor_ids == data["competitor_ids"]


def test_none_is_exclusive():
    good = MarketWrite.model_validate(payload([], True))
    assert good.no_competitors is True
    with pytest.raises(ValidationError):
        MarketWrite.model_validate(payload(["00123456789"], True))


@pytest.mark.parametrize("ids", [[""], ["ABC-12"], ["中文"], ["A_B"]])
def test_reject_bad_ids(ids):
    with pytest.raises(ValidationError):
        MarketWrite.model_validate(payload(ids))


@pytest.mark.parametrize(
    "ids",
    [["1"], ["ABC123"], ["a1Z0"], ["A" * 256], [str(i) for i in range(51)], ["1", "1"]],
)
def test_accept_alphanumeric_ids_without_length_or_count_limits(ids):
    result = MarketWrite.model_validate(payload(ids))
    assert result.competitor_ids == ids
