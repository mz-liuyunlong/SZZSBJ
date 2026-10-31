"""Diagnostic pages fetch evidence by exact Listing identity with bounded query count."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.modules.data_pages.models import ListingManagementCurrentMart
from app.modules.listing_rule_config.preview import ListingEvaluationPreviewService
from app.modules.listing_rule_config.schemas import ListingGradeRuleConfig


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


def listing(value: int, account: str, msku: str | None):
    return ListingManagementCurrentMart(
        id=UUID(int=value),
        source_account_ref=account,
        store_id="synthetic-store",
        item_id="synthetic-item",
        msku=msku,
    )


def fact(account: str, msku: str | None):
    return SimpleNamespace(
        source_account_ref=account,
        store_id="synthetic-store",
        item_id="synthetic-item",
        msku=msku,
    )


def test_page_prefetch_is_bounded_and_does_not_mix_account_or_msku(monkeypatch) -> None:
    first = listing(1, "synthetic-account-a", None)
    second = listing(2, "synthetic-account-b", "synthetic-msku")
    session = MagicMock(spec=Session)
    session.scalars.side_effect = [
        Rows([fact("synthetic-account-a", None), fact("synthetic-account-b", "synthetic-msku")]),
        Rows([fact("synthetic-account-a", None)]),
        Rows([]),
        Rows([fact("synthetic-account-b", None)]),
    ]
    session.execute.return_value.all.return_value = [
        ("synthetic-account-a", "synthetic-store", "synthetic-item", None, date(2026, 1, 1))
    ]
    captured = {}

    def capture(**kwargs):
        captured[kwargs["listing"].id] = kwargs
        return kwargs["listing"].id

    monkeypatch.setattr(ListingEvaluationPreviewService, "_from_evidence", staticmethod(capture))
    result = ListingEvaluationPreviewService(session).evaluate_page(
        listings=[first, second],
        cutoff=date(2026, 1, 15),
        config=ListingGradeRuleConfig(),
        rule_version=7,
    )

    assert result == {first.id: first.id, second.id: second.id}
    assert session.scalars.call_count == 4
    assert session.execute.call_count == 1
    assert len(captured[first.id]["sales"]) == 1
    assert len(captured[second.id]["sales"]) == 1
    assert len(captured[first.id]["stock"]) == 1
    assert captured[second.id]["stock"] == []
    assert captured[first.id]["prior"] == date(2026, 1, 1)
    assert captured[second.id]["prior"] is None
    assert captured[first.id]["monitor_rows"] == []
    assert len(captured[second.id]["monitor_rows"]) == 1
    sales_sql = str(session.scalars.call_args_list[0].args[0])
    assert "IS NOT DISTINCT FROM" in sales_sql


def test_page_prefetch_rejects_unbounded_or_duplicate_pages() -> None:
    session = MagicMock(spec=Session)
    service = ListingEvaluationPreviewService(session)
    sample = listing(1, "synthetic-account-a", None)

    with pytest.raises(ValueError, match="distinct listings"):
        service.evaluate_page(
            listings=[sample, sample],
            cutoff=date(2026, 1, 15),
            config=ListingGradeRuleConfig(),
            rule_version=7,
        )
    with pytest.raises(ValueError, match="1-200"):
        service.evaluate_page(
            listings=[listing(index, "synthetic-account-a", None) for index in range(1, 202)],
            cutoff=date(2026, 1, 15),
            config=ListingGradeRuleConfig(),
            rule_version=7,
        )
    session.scalars.assert_not_called()
