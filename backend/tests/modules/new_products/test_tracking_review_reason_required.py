"""Every new tracking outcome requires ten non-whitespace characters."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.api import ApiError
from app.modules.new_products.schemas import TrackingWrite
from app.modules.new_products.service import NewProductService

IDENTITY = {"source_account_ref": "primary", "store_id": "store", "item_id": "item"}
OUTCOMES = ("打品成功", "继续观察", "需要优化", "打品失败")


@pytest.mark.parametrize("decision", OUTCOMES)
@pytest.mark.parametrize("reason", ["", " \t\n　", "123456789", "12345 6789"])
def test_schema_rejects_short_reason(decision, reason):
    with pytest.raises(ValidationError):
        TrackingWrite(**IDENTITY, decision=decision, reason=reason, expected_version=0)


@pytest.mark.parametrize("decision", OUTCOMES)
def test_schema_requires_reason_and_accepts_ten_characters(decision):
    with pytest.raises(ValidationError):
        TrackingWrite(**IDENTITY, decision=decision, expected_version=0)
    got = TrackingWrite(**IDENTITY, decision=decision, reason="  12345 67890  ", expected_version=0)
    assert got.reason == "12345 67890"


@pytest.mark.parametrize("decision", OUTCOMES)
def test_service_rejects_short_reason_even_without_schema(decision):
    # No real DB or external calls: stop before any decision, score or write.
    fake = SimpleNamespace(db=object(), _listing=lambda *args, **kwargs: object())
    body = SimpleNamespace(**IDENTITY, decision=decision, reason="12345 6789", expected_version=0)
    with pytest.raises(ApiError) as exc:
        NewProductService.save_tracking(fake, frozenset({"primary"}), body, "actor")
    assert exc.value.status_code == 422
