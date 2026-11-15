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


@pytest.mark.parametrize("method", ["save_market", "purchase"])
def test_missing_wfs_day_blocks_write_before_touching_database(method):
    fake = _fake_service()
    body = SimpleNamespace(source_account_ref="a", store_id="s", item_id="123")
    with pytest.raises(Exception) as exc:
        getattr(NewProductService, method)(fake, {"a"}, body, "actor")
    assert type(exc.value).__name__ == "ApiError"
