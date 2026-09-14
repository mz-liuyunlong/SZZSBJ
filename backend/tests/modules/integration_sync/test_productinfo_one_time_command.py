from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.config import AppEnvironment
from app.modules.integration_sync.product_info_runner import ProductInfoOneTimeRunResult
from scripts import run_productinfo_once as command


def test_command_requires_explicit_one_time_authorization_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PRODUCT_INFO_ONE_TIME_RUN_AUTHORIZED", raising=False)
    monkeypatch.setattr(command, "get_settings", lambda: (_ for _ in ()).throw(AssertionError()))

    assert command.main() == 2


def test_dwd_execute_gate_requires_one_time_authorization_and_all_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        app_env=AppEnvironment.PRODUCTION,
        lingxing_enable_token_requests=True,
        lingxing_enable_real_calls=True,
        lingxing_dry_run=False,
        lingxing_allow_raw_write=True,
        lingxing_allow_structured_write=True,
        lingxing_enable_batch_product_info_requests=True,
    )
    monkeypatch.delenv("PRODUCT_INFO_ONE_TIME_RUN_AUTHORIZED", raising=False)
    assert command._dwd_write_is_authorized(settings) is False

    monkeypatch.setenv("PRODUCT_INFO_ONE_TIME_RUN_AUTHORIZED", "true")
    assert command._dwd_write_is_authorized(settings) is True

    settings.lingxing_allow_structured_write = False
    assert command._dwd_write_is_authorized(settings) is False


def test_product_bootstrap_authorization_is_independent_from_dwd_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCT_INFO_ONE_TIME_RUN_AUTHORIZED", "true")
    monkeypatch.delenv("PRODUCT_INFO_PRODUCT_BOOTSTRAP_AUTHORIZED", raising=False)

    assert command._exact_true("PRODUCT_INFO_ONE_TIME_RUN_AUTHORIZED") is True
    assert command._exact_true("PRODUCT_INFO_PRODUCT_BOOTSTRAP_AUTHORIZED") is False


def test_non_dry_run_injects_executor_and_keeps_bootstrap_disabled(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = SimpleNamespace(
        app_env=AppEnvironment.PRODUCTION,
        lingxing_enable_token_requests=True,
        lingxing_enable_real_calls=True,
        lingxing_dry_run=False,
        lingxing_allow_raw_write=True,
        lingxing_allow_structured_write=True,
        lingxing_enable_batch_product_info_requests=True,
    )
    result = ProductInfoOneTimeRunResult(
        dry_run=False,
        bootstrap_skipped_authorization=True,
        active_identity_count=1,
        work_items_planned=1,
        work_items_succeeded=1,
        records_seen=1,
        snapshots_written=1,
        images_written=0,
        tags_written=0,
        products_would_create=0,
        products_would_link=0,
        products_created=0,
        products_linked=0,
        skipped_missing_sku_code=0,
        skipped_missing_product_name=0,
        skipped_duplicate_sku_code=0,
        skipped_existing_deleted_product=0,
    )
    session = MagicMock()
    client = MagicMock()
    executor = MagicMock()
    runner = MagicMock()
    runner.run.return_value = result
    runner_factory = MagicMock(return_value=runner)

    monkeypatch.setenv("PRODUCT_INFO_ONE_TIME_RUN_AUTHORIZED", "true")
    monkeypatch.delenv("PRODUCT_INFO_PRODUCT_BOOTSTRAP_AUTHORIZED", raising=False)
    monkeypatch.setenv("PRODUCT_INFO_SOURCE_ACCOUNT_REF", "synthetic-account")
    monkeypatch.setattr(command, "get_settings", lambda: settings)
    monkeypatch.setattr(command, "get_session_factory", lambda: lambda: nullcontext(session))
    monkeypatch.setattr(command, "product_info_client", lambda: nullcontext(client))
    monkeypatch.setattr(command, "LingxingProductInfoExecutor", lambda *_args, **_kwargs: executor)
    monkeypatch.setattr(command, "ProductInfoOneTimeRunner", runner_factory)

    assert command.main() == 0
    runner_factory.assert_called_once_with(session, executor=executor)
    runner.run.assert_called_once_with(
        source_account_ref="synthetic-account",
        dry_run=False,
        dwd_write_authorized=True,
        product_bootstrap_authorized=False,
    )
    output = capsys.readouterr().out
    assert "products_created=0" in output
    assert "Authorization" not in output


def test_count_only_output_contains_no_product_or_credential_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    command._print_result(
        ProductInfoOneTimeRunResult(
            dry_run=True,
            bootstrap_skipped_authorization=False,
            active_identity_count=1,
            work_items_planned=1,
            work_items_succeeded=0,
            records_seen=0,
            snapshots_written=0,
            images_written=0,
            tags_written=0,
            products_would_create=1,
            products_would_link=0,
            products_created=0,
            products_linked=0,
            skipped_missing_sku_code=0,
            skipped_missing_product_name=0,
            skipped_duplicate_sku_code=0,
            skipped_existing_deleted_product=0,
        )
    )

    output = capsys.readouterr().out
    assert "SYNTHETIC-SKU" not in output
    assert "Synthetic Product" not in output
    assert "https://" not in output
    assert "Authorization" not in output
