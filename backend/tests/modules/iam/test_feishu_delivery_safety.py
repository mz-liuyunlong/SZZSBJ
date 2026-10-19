from __future__ import annotations

import io
import urllib.error
from email.message import Message

import pytest

from app.modules.iam.feishu_service import FeishuDeliveryError, FeishuService

CANARY = "synthetic-secret-canary"


def _service() -> FeishuService:
    return FeishuService(
        enabled=True,
        base_url="https://feishu.invalid",
        app_id="synthetic-app",
        app_secret="synthetic-secret",
        timeout_seconds=1,
    )


def test_http_error_does_not_read_or_chain_provider_body(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.HTTPError(
        "https://feishu.invalid",
        502,
        "bad gateway",
        Message(),
        io.BytesIO(CANARY.encode()),
    )
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error)
    )

    with pytest.raises(FeishuDeliveryError) as raised:
        _service()._post_json("https://feishu.invalid", {}, headers={})

    assert raised.value.reason_code == "http_error"
    assert raised.value.http_status == 502
    assert raised.value.__cause__ is None
    assert CANARY not in str(raised.value)


def test_provider_message_is_discarded_from_error() -> None:
    with pytest.raises(FeishuDeliveryError) as raised:
        _service()._ensure_success({"code": 19001, "msg": CANARY}, action="synthetic")

    assert raised.value.reason_code == "provider_rejected"
    assert raised.value.provider_code == 19001
    assert CANARY not in str(raised.value)
