from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.modules.woocommerce_config import service
from app.modules.woocommerce_config.schemas import WooCommerceStoreUpdate


@pytest.mark.parametrize("environment", ["local", "test", "production"])
@pytest.mark.parametrize("code", ["OK", "WOO_AUTH_FAILED"])
def test_explicit_probe_records_result_in_every_environment(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    code: str,
) -> None:
    monkeypatch.setenv("APP_ENV", environment)
    store_id = uuid4()
    session = Mock()
    monkeypatch.setattr(service, "get_session_factory", lambda: lambda: nullcontext(session))
    monkeypatch.setattr(
        service.repository,
        "get_store",
        lambda *_a, **_k: {
            "store_url": "https://store.example.com",
            "consumer_key_ciphertext": "encrypted-key",
            "consumer_secret_ciphertext": "encrypted-secret",
        },
    )
    monkeypatch.setattr(service, "_decrypt", lambda value: "synthetic-" + value)
    probe = Mock(return_value=code)
    record = Mock(return_value=True)
    audit = Mock()
    monkeypatch.setattr(service, "probe_connection", probe)
    monkeypatch.setattr(service.repository, "update_test_result", record)
    monkeypatch.setattr(service.repository, "add_audit", audit)

    register = Mock()
    monkeypatch.setattr("app.modules.woocommerce_products.task_center.register_store", register)

    result = service.test_store(store_id, actor="synthetic-actor")
    if code == "OK":
        register.assert_not_called()
    else:
        register.assert_called_once_with(session, store_id, enabled=False)

    probe.assert_called_once_with(
        "https://store.example.com", "synthetic-encrypted-key", "synthetic-encrypted-secret"
    )
    assert result.ok is (code == "OK")
    assert result.code == code
    assert record.call_args.kwargs["ok"] is result.ok
    assert record.call_args.kwargs["code"] == code
    audit.assert_called_once_with(
        session, actor="synthetic-actor", action="woocommerce.store.test", store_id=store_id
    )
    session.commit.assert_called_once()


@pytest.mark.parametrize(
    ("catalog_present", "catalog_has_rows", "expected_code"),
    [
        (False, False, "WOO_DOMAIN_REQUIRES_NEW_CREDENTIALS"),
        (True, False, "WOO_DOMAIN_REQUIRES_NEW_CREDENTIALS"),
        (True, True, "WOO_STORE_ORIGIN_IMMUTABLE"),
    ],
)
def test_domain_change_requires_new_credentials(
    monkeypatch: pytest.MonkeyPatch,
    catalog_present: bool,
    catalog_has_rows: bool,
    expected_code: str,
) -> None:
    session = Mock()
    catalog_check = Mock()
    catalog_check.scalar_one.return_value = catalog_present
    row_check = Mock()
    row_check.scalar_one.return_value = catalog_has_rows
    session.execute.side_effect = [catalog_check, row_check]
    monkeypatch.setattr(service, "get_session_factory", lambda: lambda: nullcontext(session))
    monkeypatch.setattr(
        service.repository,
        "get_store",
        lambda *_a, **_k: {
            "store_url": "https://old.example.com",
        },
    )
    with pytest.raises(service.WooCommerceConfigError) as exc_info:
        service.update_store(
            uuid4(),
            WooCommerceStoreUpdate(
                name="Synthetic shop",
                store_url="https://new.example.com",
                enabled=False,
            ),
            actor="synthetic-actor",
        )
    assert exc_info.value.code == expected_code
    assert session.execute.call_count == (2 if catalog_present else 1)
    assert "to_regclass" in str(session.execute.call_args_list[0].args[0])
    if catalog_present:
        assert "dim_woocommerce_products" in str(session.execute.call_args_list[1].args[0])
    session.commit.assert_not_called()
