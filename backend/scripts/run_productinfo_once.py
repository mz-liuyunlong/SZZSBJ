from __future__ import annotations

import os
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import AppEnvironment, get_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.modules.integration_sync.handlers.lingxing_product_info_executor import (  # noqa: E402
    LingxingProductInfoExecutor,
    product_info_client,
)
from app.modules.integration_sync.product_info_runner import (  # noqa: E402
    ProductInfoOneTimeRunError,
    ProductInfoOneTimeRunner,
    ProductInfoOneTimeRunResult,
)

SAFE_ACCOUNT_REF = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class ProductInfoRuntimeSettings(Protocol):
    app_env: AppEnvironment
    lingxing_enable_token_requests: bool
    lingxing_enable_real_calls: bool
    lingxing_dry_run: bool
    lingxing_allow_raw_write: bool
    lingxing_allow_structured_write: bool
    lingxing_enable_batch_product_info_requests: bool


def main() -> int:
    if not _exact_true("PRODUCT_INFO_ONE_TIME_RUN_AUTHORIZED"):
        print("PRODUCT_INFO_ONE_TIME_RUN_REQUIRES_AUTHORIZATION")
        return 2
    source_account_ref = os.getenv("PRODUCT_INFO_SOURCE_ACCOUNT_REF", "")
    if not SAFE_ACCOUNT_REF.fullmatch(source_account_ref):
        print("PRODUCT_INFO_SOURCE_ACCOUNT_REF_INVALID")
        return 2
    try:
        settings = get_settings()
        dwd_write_authorized = _dwd_write_is_authorized(settings)
        product_bootstrap_authorized = _exact_true("PRODUCT_INFO_PRODUCT_BOOTSTRAP_AUTHORIZED")
        if not settings.lingxing_dry_run and not dwd_write_authorized:
            raise ProductInfoOneTimeRunError("PRODUCT_INFO_EXECUTION_SETTINGS_NOT_AUTHORIZED")
        with get_session_factory()() as session:
            if settings.lingxing_dry_run:
                result = ProductInfoOneTimeRunner(session).run(
                    source_account_ref=source_account_ref,
                    dry_run=True,
                    product_bootstrap_authorized=product_bootstrap_authorized,
                )
            else:
                with product_info_client() as client:
                    result = ProductInfoOneTimeRunner(
                        session,
                        executor=LingxingProductInfoExecutor(session, client=client),
                    ).run(
                        source_account_ref=source_account_ref,
                        dry_run=False,
                        dwd_write_authorized=dwd_write_authorized,
                        product_bootstrap_authorized=product_bootstrap_authorized,
                    )
    except ProductInfoOneTimeRunError as error:
        print(str(error))
        return 2
    except Exception:
        print("PRODUCT_INFO_ONE_TIME_RUN_FAILED")
        return 1
    _print_result(result)
    return 0


def _print_result(result: ProductInfoOneTimeRunResult) -> None:
    for name, value in asdict(result).items():
        print(f"{name}={str(value).lower() if isinstance(value, bool) else value}")


def _dwd_write_is_authorized(settings: ProductInfoRuntimeSettings) -> bool:
    return bool(
        _exact_true("PRODUCT_INFO_ONE_TIME_RUN_AUTHORIZED")
        and settings.app_env is AppEnvironment.PRODUCTION
        and settings.lingxing_enable_token_requests
        and settings.lingxing_enable_real_calls
        and not settings.lingxing_dry_run
        and settings.lingxing_allow_raw_write
        and settings.lingxing_allow_structured_write
        and settings.lingxing_enable_batch_product_info_requests
    )


def _exact_true(name: str) -> bool:
    return os.getenv(name, "").casefold() == "true"


if __name__ == "__main__":
    raise SystemExit(main())
