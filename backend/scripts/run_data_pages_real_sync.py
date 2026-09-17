import app.modules.integration_sync.data_pages_business_rules as business_rules
from app.modules.integration_sync.data_pages_business_rules_v4 import DataPagesRealSyncRunner
from app.modules.integration_sync.data_pages_real_sync import (
    DataPagesRealSyncError,
    DataPagesRealSyncSummary,
    _rows_for,
    _stable_hash,
    data_pages_response_succeeded,
)


def main() -> None:
    """Run the governed CLI with the latest data-pages business-rule runner."""
    business_rules.DataPagesRealSyncRunner = DataPagesRealSyncRunner
    business_rules.main()


__all__ = [
    "DataPagesRealSyncError",
    "DataPagesRealSyncRunner",
    "DataPagesRealSyncSummary",
    "_rows_for",
    "_stable_hash",
    "data_pages_response_succeeded",
    "main",
]


if __name__ == "__main__":
    main()
