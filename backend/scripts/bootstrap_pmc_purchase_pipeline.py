"""Explicit metadata registration; never calls Lingxing or enables real execution."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.db.model_registry import register_productlist_sync_models  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.modules.integration_sync.catalog import (  # noqa: E402
    validate_pmc_purchase_source_account_ref,
)
from app.modules.integration_sync.pmc_purchase_pipeline_repository import (  # noqa: E402
    PurchasePipelineRepository,
    purchase_connection,
)


def main() -> int:
    if os.getenv("PMC_PURCHASE_PIPELINE_BOOTSTRAP_AUTHORIZED", "").lower() != "true":
        print("PMC_PURCHASE_PIPELINE_BOOTSTRAP_REQUIRES_AUTHORIZATION")
        return 2
    try:
        account = validate_pmc_purchase_source_account_ref(
            os.getenv("PMC_PURCHASE_SOURCE_ACCOUNT_REF", "")
        )
        register_productlist_sync_models()
        with purchase_connection(get_engine()) as connection:
            if connection is None:
                print("SYNC_PURCHASE_RUN_ACTIVE")
                return 2
            with Session(bind=connection) as session:
                PurchasePipelineRepository(session).register(account)
                session.commit()
    except Exception:
        print("PMC_PURCHASE_PIPELINE_BOOTSTRAP_FAILED")
        return 1
    print("PMC_PURCHASE_PIPELINE_REGISTERED_EXECUTION_UNCHANGED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
