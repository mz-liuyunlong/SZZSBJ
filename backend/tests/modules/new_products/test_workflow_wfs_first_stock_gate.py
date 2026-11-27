from types import SimpleNamespace

import pytest

from app.modules.new_products.service import NewProductService


class _NoWrite:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("Missing WFS must reject before a database write")


def _fake_service():
    def _listing(*_args):
        return SimpleNamespace(first_wfs_available_date_la=None)

    def _score(*_args):
        raise AssertionError("Missing WFS must reject before score computation")

    return SimpleNamespace(_listing=_listing, score=_score, db=_NoWrite())


def test_missing_wfs_day_still_blocks_market_score():
    fake = _fake_service()
    body = SimpleNamespace(source_account_ref="a", store_id="s", item_id="123")
    with pytest.raises(Exception) as exc:
        NewProductService.save_market(fake, {"a"}, body, "actor")
    assert type(exc.value).__name__ == "ApiError"


def test_missing_wfs_day_does_not_block_purchase():
    fake = _fake_service()
    fake._final_decisions = lambda _keys: {}
    fake.db.rollback = lambda: None
    body = SimpleNamespace(source_account_ref="a", store_id="s", item_id="123")
    # Reaching the transaction lock proves the obsolete WFS gate is gone.
    with pytest.raises(AssertionError, match="Missing WFS must reject before a database write"):
        NewProductService.purchase(fake, {"a"}, body, "actor")
