import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.modules.integration_sync.handlers.lingxing_batch_product_info import (
    BatchProductInfoOutboundDisabled,
    LingxingBatchGetProductInfoSyncHandler,
    ordered_id_hash,
)
from app.modules.integration_sync.importer import (
    LocalProductListRawImportService,
    LocalRawImportError,
    validate_productlist_capture,
)

RUN_ID = UUID("00000000-0000-0000-0000-000000000001")


def _capture(root: Path, *, corrupt: bool = False) -> Path:
    run_dir = root / "outside-repository" / "synthetic-run"
    pages = run_dir / "pages"
    pages.mkdir(parents=True)
    payloads = [
        (
            "page_000001_offset_0.json",
            {"code": 200, "total": 2, "data": [{"id": "synthetic-a"}]},
        ),
        (
            "page_000002_offset_1.json",
            {"code": 200, "total": 2, "data": [{"id": "synthetic-b"}]},
        ),
    ]
    checksums: list[str] = []
    for name, payload in payloads:
        content = json.dumps(payload, separators=(",", ":"))
        path = pages / name
        path.write_text(content, encoding="utf-8")
        digest = "0" * 64 if corrupt else hashlib.sha256(content.encode()).hexdigest()
        checksums.append(f"{digest}  pages/{name}")
    (run_dir / "checksums.sha256").write_text("\n".join(checksums), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "validation_run_id": "synthetic-run",
                "pages_written": 2,
                "page_size": 1,
                "total_value": 2,
                "total_captured": 2,
                "stopped_reason": "total_reached",
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_local_capture_validates_before_returning_payload(tmp_path: Path) -> None:
    run_dir = _capture(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    capture = validate_productlist_capture(run_dir, repository_root=repository)
    assert capture.validation_run_id == "synthetic-run"
    assert capture.total_captured == 2
    assert [page.offset for page in capture.pages] == [0, 1]
    assert [page.length for page in capture.pages] == [1, 1]
    assert len({page.response_hash for page in capture.pages}) == 2


def test_local_capture_rejects_checksum_tamper(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(LocalRawImportError, match="CHECKSUM_MISMATCH"):
        validate_productlist_capture(_capture(tmp_path, corrupt=True), repository_root=repository)


def test_local_capture_rejects_repository_internal_directory(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    run_dir = _capture(repository)
    with pytest.raises(LocalRawImportError, match="INSIDE_REPOSITORY"):
        validate_productlist_capture(run_dir, repository_root=repository)


def test_local_capture_rejects_checksum_path_traversal(tmp_path: Path) -> None:
    run_dir = _capture(tmp_path)
    (run_dir / "checksums.sha256").write_text(
        f"{'0' * 64}  ../outside.json",
        encoding="utf-8",
    )
    repository = tmp_path / "repository"
    repository.mkdir()

    with pytest.raises(LocalRawImportError, match="CHECKSUM_PATH_INVALID"):
        validate_productlist_capture(run_dir, repository_root=repository)


def test_local_capture_rejects_unlisted_page(tmp_path: Path) -> None:
    run_dir = _capture(tmp_path)
    (run_dir / "pages" / "page_000003_offset_2.json").write_text(
        "{}",
        encoding="utf-8",
    )
    repository = tmp_path / "repository"
    repository.mkdir()

    with pytest.raises(LocalRawImportError, match="PAGE_SET_MISMATCH"):
        validate_productlist_capture(run_dir, repository_root=repository)


def test_local_import_publishes_identities_then_reconciles_active_set(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    capture = validate_productlist_capture(
        _capture(tmp_path),
        repository_root=repository_root,
    )
    session = MagicMock(spec=Session)
    service = LocalProductListRawImportService(session)
    service.repository = MagicMock()
    service.repository.get_interface_by_key.return_value = SimpleNamespace(id=RUN_ID)
    service.repository.get_retention_policy.return_value = SimpleNamespace(id=RUN_ID)
    service.repository.find_blob_by_hash.return_value = None
    service.repository.get_lingxing_identity.return_value = None
    service.repository.add_raw_blob.side_effect = lambda record: record
    service.repository.add_raw_request_ref.side_effect = lambda record: record

    result = service.import_capture(capture, source_account_ref="default")

    assert result.total_captured == 2
    assert result.sku_identity_count == 2
    assert service.repository.add_identity.call_count == 2
    assert service.repository.add_parse_job.call_count == 2
    assert service.repository.add_lineage.call_count == 2
    assert service.repository.deactivate_absent_identities.call_args.kwargs["observed_ids"] == {
        "synthetic-a",
        "synthetic-b",
    }
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_local_import_failure_rolls_back_without_deactivation(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    capture = validate_productlist_capture(
        _capture(tmp_path),
        repository_root=repository_root,
    )
    session = MagicMock(spec=Session)
    service = LocalProductListRawImportService(session)
    service.repository = MagicMock()
    service.repository.get_interface_by_key.return_value = SimpleNamespace(id=RUN_ID)
    service.repository.get_retention_policy.return_value = SimpleNamespace(id=RUN_ID)
    service.repository.find_blob_by_hash.return_value = None
    service.repository.add_raw_blob.side_effect = lambda record: record
    service.repository.add_raw_request_ref.side_effect = lambda record: record
    service.repository.add_productlist_refs.side_effect = RuntimeError("safe")

    with pytest.raises(RuntimeError, match="safe"):
        service.import_capture(capture, source_account_ref="default")

    service.repository.deactivate_absent_identities.assert_not_called()
    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()


def test_batch_plan_is_deterministic_and_safe() -> None:
    handler = LingxingBatchGetProductInfoSyncHandler()
    plan = handler.build_plan(
        run_id=RUN_ID,
        source_account_ref="default",
        lingxing_sku_ids=["synthetic-c", "synthetic-a", "synthetic-b"],
        batch_size=2,
    )
    assert [item.id_count for item in plan.work_items] == [2, 1]
    assert plan.work_items[0].request_safe_params == {
        "batch_no": 1,
        "id_count": 2,
        "id_hash": ordered_id_hash(["synthetic-a", "synthetic-b"]),
    }
    assert "synthetic" not in json.dumps(plan.work_items[0].request_safe_params)
    assert [item.lingxing_sku_id for item in plan.batch_items] == [
        "synthetic-a",
        "synthetic-b",
        "synthetic-c",
    ]


def test_batch_handler_transport_is_explicitly_disabled() -> None:
    with pytest.raises(BatchProductInfoOutboundDisabled):
        LingxingBatchGetProductInfoSyncHandler().execute(RUN_ID)
