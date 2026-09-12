from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.integrations.lingxing.security import canonical_json, redact_json
from app.modules.integration_sync.models import (
    ApiRawBlob,
    ApiRawRequestRef,
    DataLineage,
    IntegrationSyncRun,
    IntegrationSyncRunEvent,
    IntegrationSyncRunWorkItem,
    LingxingProductListSkuRef,
    ParseJob,
)
from app.modules.integration_sync.parsers.lingxing_product_list import (
    parse_productlist_sku_ids,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository
from app.modules.sku_detail.models import LingxingSkuIdentity

DEFAULT_PRODUCTLIST_RAW_RUN_DIR = Path(
    "/Users/sakura/Desktop/YC-System/local-raw-captures/lingxing/productList/"
    "lingxing_product_list_20260911T195715Z_636b2f7d"
)
PAGE_NAME = re.compile(r"page_(?P<page>\d{6})_offset_(?P<offset>\d+)\.json")
MAX_MANIFEST_BYTES = 1_048_576
MAX_PAGE_BYTES = 10_485_760


class LocalRawImportError(RuntimeError):
    """Safe import error; messages contain codes, never source values."""


@dataclass(frozen=True, slots=True)
class ValidatedRawPage:
    page_no: int
    offset: int
    length: int
    payload: JsonValue
    sku_ids: tuple[str, ...]
    response_hash: str
    payload_bytes: int


@dataclass(frozen=True, slots=True)
class ValidatedProductListCapture:
    validation_run_id: str
    pages: tuple[ValidatedRawPage, ...]
    total_value: int
    total_captured: int
    stopped_reason: str


@dataclass(frozen=True, slots=True)
class LocalRawImportResult:
    run_id: UUID
    total_captured: int
    sku_identity_count: int
    response_hashes_count: int


def validate_productlist_capture(
    raw_run_dir: Path,
    *,
    repository_root: Path,
) -> ValidatedProductListCapture:
    _reject_unsafe_root(raw_run_dir, repository_root)
    manifest_path = raw_run_dir / "manifest.json"
    checksums_path = raw_run_dir / "checksums.sha256"
    manifest = _read_json(manifest_path, MAX_MANIFEST_BYTES)
    if not isinstance(manifest, dict):
        raise LocalRawImportError("LOCAL_RAW_MANIFEST_INVALID")
    expected_hashes = _read_checksums(checksums_path)
    page_paths = sorted((raw_run_dir / "pages").glob("*.json"))
    relative_pages = {path.relative_to(raw_run_dir).as_posix() for path in page_paths}
    if set(expected_hashes) != relative_pages or not relative_pages:
        raise LocalRawImportError("LOCAL_RAW_PAGE_SET_MISMATCH")
    for path in page_paths:
        if path.is_symlink() or path.stat().st_size > MAX_PAGE_BYTES:
            raise LocalRawImportError("LOCAL_RAW_PAGE_UNSAFE")
        relative = path.relative_to(raw_run_dir).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected_hashes[relative]:
            raise LocalRawImportError("LOCAL_RAW_CHECKSUM_MISMATCH")

    pages: list[ValidatedRawPage] = []
    provider_totals: set[int] = set()
    expected_offset = 0
    for path in page_paths:
        match = PAGE_NAME.fullmatch(path.name)
        if match is None:
            raise LocalRawImportError("LOCAL_RAW_PAGE_NAME_INVALID")
        page_no = int(match.group("page"))
        offset = int(match.group("offset"))
        if page_no != len(pages) + 1 or offset != expected_offset:
            raise LocalRawImportError("LOCAL_RAW_PAGINATION_GAP")
        stored = _read_json(path, MAX_PAGE_BYTES)
        response = _response_payload(stored)
        length = _request_length(stored, manifest)
        provider_total = _provider_total(response)
        if provider_total is not None:
            provider_totals.add(provider_total)
        sku_ids = parse_productlist_sku_ids(response)
        redacted = redact_json(response)
        encoded = canonical_json(redacted).encode("utf-8")
        pages.append(
            ValidatedRawPage(
                page_no=page_no,
                offset=offset,
                length=length,
                payload=redacted,
                sku_ids=tuple(sku_ids),
                response_hash=hashlib.sha256(encoded).hexdigest(),
                payload_bytes=len(encoded),
            )
        )
        expected_offset += len(sku_ids)

    run_id = manifest.get("validation_run_id")
    total_captured = _manifest_int(manifest, "total_captured")
    total_value = _manifest_int(manifest, "total_value")
    pages_written = _manifest_int(manifest, "pages_written")
    stopped_reason = manifest.get("stopped_reason")
    if (
        not isinstance(run_id, str)
        or not run_id.strip()
        or pages_written != len(pages)
        or total_captured != sum(len(page.sku_ids) for page in pages)
        or total_value != total_captured
        or provider_totals != {total_value}
        or stopped_reason != "total_reached"
    ):
        raise LocalRawImportError("LOCAL_RAW_MANIFEST_RECONCILIATION_FAILED")
    all_ids = [sku_id for page in pages for sku_id in page.sku_ids]
    if len(all_ids) != len(set(all_ids)):
        raise LocalRawImportError("LOCAL_RAW_SKU_ID_DUPLICATE")
    return ValidatedProductListCapture(
        validation_run_id=run_id,
        pages=tuple(pages),
        total_value=total_value,
        total_captured=total_captured,
        stopped_reason=stopped_reason,
    )


class LocalProductListRawImportService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = IntegrationSyncRepository(session)

    def import_capture(
        self,
        capture: ValidatedProductListCapture,
        *,
        source_account_ref: str,
    ) -> LocalRawImportResult:
        if not source_account_ref or source_account_ref != source_account_ref.strip():
            raise LocalRawImportError("SOURCE_ACCOUNT_REF_INVALID")
        interface = self.repository.get_interface_by_key("lingxing", "productList")
        policy = self.repository.get_retention_policy("lingxing-productlist-v1")
        if interface is None or policy is None:
            raise LocalRawImportError("IMPORT_METADATA_NOT_BOOTSTRAPPED")
        now = datetime.now(UTC)
        run = IntegrationSyncRun(
            id=uuid4(),
            config_id=None,
            interface_id=interface.id,
            provider="lingxing",
            interface_key="productList",
            source_account_ref=source_account_ref,
            trigger_type="import",
            status="running",
            idempotency_key=f"productlist-import:{capture.validation_run_id}:{source_account_ref}",
            reason="controlled_local_raw_import",
            queued_at=now,
            started_at=now,
            work_items_total=len(capture.pages),
            work_items_succeeded=0,
            work_items_failed=0,
            records_seen=0,
            records_written=0,
        )
        try:
            self.repository.add_run(run)
            self._event(run.id, 1, None, "running", "SYNC_IMPORT_STARTED", now)
            all_ids: set[str] = set()
            for page in capture.pages:
                work = IntegrationSyncRunWorkItem(
                    id=uuid4(),
                    run_id=run.id,
                    ordinal=page.page_no,
                    request_kind="offset_page",
                    status="succeeded",
                    attempt_count=1,
                    offset_value=page.offset,
                    length_value=page.length,
                    request_safe_params={
                        "offset": page.offset,
                        "length": page.length,
                    },
                    response_count=len(page.sku_ids),
                    started_at=now,
                    finished_at=now,
                )
                self.repository.add_work_items([work])
                blob = self.repository.find_blob_by_hash(page.response_hash)
                if blob is None:
                    blob = self.repository.add_raw_blob(
                        ApiRawBlob(
                            id=uuid4(),
                            response_hash=page.response_hash,
                            payload_json=page.payload,
                            payload_bytes=page.payload_bytes,
                            content_type="application/json",
                            storage_mode="database",
                            retention_policy_id=policy.id,
                            received_at=now,
                        )
                    )
                raw_ref = self.repository.add_raw_request_ref(
                    ApiRawRequestRef(
                        id=uuid4(),
                        run_id=run.id,
                        work_item_id=work.id,
                        raw_blob_id=blob.id,
                        request_kind="offset_page",
                        attempt_no=1,
                        request_safe_params=work.request_safe_params,
                        http_status=None,
                        provider_code=_provider_code(page.payload),
                        is_success=True,
                        response_count=len(page.sku_ids),
                        requested_at=now,
                        received_at=now,
                    )
                )
                refs = [
                    LingxingProductListSkuRef(
                        id=uuid4(),
                        run_id=run.id,
                        raw_request_ref_id=raw_ref.id,
                        source_account_ref=source_account_ref,
                        lingxing_sku_id=sku_id,
                        source_item_ordinal=ordinal,
                        observed_at=now,
                    )
                    for ordinal, sku_id in enumerate(page.sku_ids)
                ]
                self.repository.add_productlist_refs(refs)
                all_ids.update(page.sku_ids)
                identities = self._upsert_identities(run.id, source_account_ref, page.sku_ids, now)
                parse_job = ParseJob(
                    id=uuid4(),
                    run_id=run.id,
                    raw_request_ref_id=raw_ref.id,
                    parser_key="lingxing.product_list.v1",
                    parser_version="v1",
                    target_layer="DWD",
                    status="succeeded",
                    records_seen=len(page.sku_ids),
                    records_written=len(page.sku_ids),
                    records_rejected=0,
                    started_at=now,
                    finished_at=now,
                )
                self.repository.add_parse_job(parse_job)
                self.repository.add_lineage(
                    [
                        DataLineage(
                            id=uuid4(),
                            run_id=run.id,
                            parse_job_id=parse_job.id,
                            raw_request_ref_id=raw_ref.id,
                            raw_blob_id=blob.id,
                            source_path=f"$.data[{ordinal}].id",
                            target_table="dwd_lingxing_sku_identity_index",
                            target_record_id=str(identity.id),
                            target_field="lingxing_sku_id",
                            transform_key="lingxing.product_list.identity",
                            transform_version="v1",
                        )
                        for ordinal, identity in enumerate(identities)
                    ]
                )
                self._event(
                    run.id,
                    page.page_no + 1,
                    None,
                    None,
                    "PARSE_JOB_SUCCEEDED",
                    now,
                    event_type="parse",
                )
            self.repository.deactivate_absent_identities(
                source_account_ref=source_account_ref,
                observed_ids=all_ids,
                run_id=run.id,
                inactive_at=now,
            )
            run.status = "succeeded"
            run.finished_at = now
            run.work_items_succeeded = len(capture.pages)
            run.records_seen = capture.total_captured
            run.records_written = capture.total_captured
            self._event(
                run.id,
                len(capture.pages) + 2,
                "running",
                "succeeded",
                "SYNC_IMPORT_SUCCEEDED",
                now,
            )
            self.session.flush()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return LocalRawImportResult(
            run_id=run.id,
            total_captured=capture.total_captured,
            sku_identity_count=len(all_ids),
            response_hashes_count=len({page.response_hash for page in capture.pages}),
        )

    def _upsert_identities(
        self,
        run_id: UUID,
        source_account_ref: str,
        sku_ids: tuple[str, ...],
        observed_at: datetime,
    ) -> list[LingxingSkuIdentity]:
        identities: list[LingxingSkuIdentity] = []
        for sku_id in sku_ids:
            identity = self.repository.get_lingxing_identity(source_account_ref, sku_id)
            if identity is None:
                identity = LingxingSkuIdentity(
                    id=uuid4(),
                    provider="lingxing",
                    source_account_ref=source_account_ref,
                    lingxing_sku_id=sku_id,
                    mapping_status="unmapped",
                    is_active=True,
                    first_seen_run_id=run_id,
                    last_seen_run_id=run_id,
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                )
                self.repository.add_identity(identity)
            else:
                identity.is_active = True
                identity.last_seen_run_id = run_id
                identity.last_seen_at = observed_at
                identity.inactive_at = None
            identities.append(identity)
        return identities

    def _event(
        self,
        run_id: UUID,
        sequence_no: int,
        from_status: str | None,
        to_status: str | None,
        message_code: str,
        occurred_at: datetime,
        *,
        event_type: str = "state_transition",
    ) -> None:
        self.repository.add_event(
            IntegrationSyncRunEvent(
                run_id=run_id,
                sequence_no=sequence_no,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                message_code=message_code,
                safe_details=None,
                occurred_at=occurred_at,
                actor_ref="local-import",
            )
        )


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("LIVE_IMPORT_SKIPPED_DATABASE_URL_MISSING")
        return 0
    url = make_url(database_url)
    if url.drivername != "postgresql+psycopg" or url.host not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        print("LIVE_IMPORT_SKIPPED_DATABASE_NOT_CONFIRMED_LOCAL")
        return 2
    raw_path = Path(
        os.environ.get("LINGXING_PRODUCTLIST_RAW_RUN_DIR", str(DEFAULT_PRODUCTLIST_RAW_RUN_DIR))
    )
    repository_root = Path(__file__).resolve().parents[4]
    capture = validate_productlist_capture(raw_path, repository_root=repository_root)
    with get_session_factory()() as session:
        result = LocalProductListRawImportService(session).import_capture(
            capture,
            source_account_ref=os.environ.get("LINGXING_SOURCE_ACCOUNT_REF", "default"),
        )
    print(
        "import_status=PASS "
        f"run_id={result.run_id} total_captured={result.total_captured} "
        f"sku_identity_count={result.sku_identity_count} "
        f"response_hashes_count={result.response_hashes_count}"
    )
    return 0


def _reject_unsafe_root(raw_run_dir: Path, repository_root: Path) -> None:
    if raw_run_dir.is_symlink() or not raw_run_dir.is_dir():
        raise LocalRawImportError("LOCAL_RAW_DIRECTORY_INVALID")
    resolved = raw_run_dir.resolve(strict=True)
    repo = repository_root.resolve(strict=True)
    if resolved == repo or repo in resolved.parents:
        raise LocalRawImportError("LOCAL_RAW_DIRECTORY_INSIDE_REPOSITORY")


def _read_checksums(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise LocalRawImportError("LOCAL_RAW_CHECKSUM_FILE_INVALID")
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise LocalRawImportError("LOCAL_RAW_CHECKSUM_FILE_INVALID")
        relative = parts[1].lstrip("*")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or not relative.startswith("pages/"):
            raise LocalRawImportError("LOCAL_RAW_CHECKSUM_PATH_INVALID")
        if relative in result:
            raise LocalRawImportError("LOCAL_RAW_CHECKSUM_DUPLICATE")
        result[relative] = parts[0].lower()
    return result


def _read_json(path: Path, max_bytes: int) -> JsonValue:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise LocalRawImportError("LOCAL_RAW_JSON_FILE_INVALID")
    try:
        value: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise LocalRawImportError("LOCAL_RAW_JSON_INVALID") from None
    return value


def _response_payload(value: JsonValue) -> JsonValue:
    if not isinstance(value, dict):
        raise LocalRawImportError("LOCAL_RAW_PAGE_INVALID")
    nested = value.get("response_json")
    return nested if nested is not None else value


def _manifest_int(manifest: dict[str, JsonValue], key: str) -> int:
    value = manifest.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LocalRawImportError("LOCAL_RAW_MANIFEST_INVALID")
    return value


def _request_length(stored: JsonValue, manifest: dict[str, JsonValue]) -> int:
    candidates: list[object] = [manifest.get("page_size"), manifest.get("length")]
    if isinstance(stored, dict):
        candidates.append(stored.get("length"))
        for key in ("request_body", "request_body_json"):
            body = stored.get(key)
            if isinstance(body, dict):
                candidates.append(body.get("length"))
    for value in candidates:
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    raise LocalRawImportError("LOCAL_RAW_PAGE_LENGTH_MISSING")


def _provider_total(response: JsonValue) -> int | None:
    if not isinstance(response, dict):
        return None
    value = response.get("total")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _provider_code(response: JsonValue) -> str | None:
    if not isinstance(response, dict):
        return None
    value = response.get("code")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value)[:64]


if __name__ == "__main__":
    raise SystemExit(main())
