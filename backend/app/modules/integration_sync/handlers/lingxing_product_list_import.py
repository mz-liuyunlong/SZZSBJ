from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.integration_sync.importer import (
    LocalProductListRawImportService,
    LocalRawImportResult,
    validate_productlist_capture,
)


class LingxingProductListImportHandler:
    handler_key = "lingxing.product_list_import.v1"
    request_kind = "offset_page"

    def __init__(self, session: Session) -> None:
        self.service = LocalProductListRawImportService(session)

    def import_directory(
        self,
        raw_run_dir: Path,
        *,
        repository_root: Path,
        source_account_ref: str,
    ) -> LocalRawImportResult:
        capture = validate_productlist_capture(raw_run_dir, repository_root=repository_root)
        return self.service.import_capture(capture, source_account_ref=source_account_ref)
