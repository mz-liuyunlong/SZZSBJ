"""Regression tests for five adjacent Listing lifecycle sales bands."""

import pytest
from pydantic import ValidationError

from app.modules.listing_rule_config.schemas import SalesTierPercents


@pytest.mark.parametrize(
    "tiers",
    [
        (50, 40, 30, 25, 20),
        (50, 50, 50, 50, 50),
    ],
)
def test_valid_five_tiers_do_not_raise_length_errors(tiers: tuple[int, ...]) -> None:
    config = SalesTierPercents(
        lt2=tiers[0],
        from2to5=tiers[1],
        from5to10=tiers[2],
        from10to20=tiers[3],
        gte20=tiers[4],
    )
    assert config.gte20 == tiers[-1]


def test_increasing_adjacent_tiers_are_rejected() -> None:
    with pytest.raises(ValidationError, match="销量阶梯百分比"):
        SalesTierPercents(lt2=50, from2to5=40, from5to10=45, from10to20=25, gte20=20)
