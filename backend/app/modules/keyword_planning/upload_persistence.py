"""Private immutable XLSX storage + account-scoped PostgreSQL source ingestion.

Must be called ONLY after RBAC + source-account + product access checks.
No HTTP upload route is automatically enabled without an explicitly configured
private storage root. Excel source rows are stored without deduplication.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .models import (
    BizKwMarketObservation,
    BizKwSourceEvent,
    BizSkuKeyword,
    DimKwTerm,
    RawKwUploadFile,
    RawKwUploadRow,
)
from .rule_gates import NORMALIZER_VERSION
from .workbook_ingestion import ParsedWorkbook, parse_keyword_xlsx

MARKET_HEADERS = {
    "搜索量": "monthly_searches",
    "月搜索量": "monthly_searches",
    "monthly searches": "monthly_searches",
    "search volume": "monthly_searches",
    "购买量": "monthly_purchases",
    "月购买量": "monthly_purchases",
    "monthly purchases": "monthly_purchases",
    "ppc": "ppc_usd",
    "ppc ($)": "ppc_usd",
    "ppc usd": "ppc_usd",
    "最低出价": "bid_min_usd",
    "min bid": "bid_min_usd",
    "最高出价": "bid_max_usd",
    "max bid": "bid_max_usd",
}


def market_observation_from_row(
    header_cells: dict[str, object],
    source_cells: dict[str, object],
) -> tuple[dict[str, int | Decimal | None], dict[str, object]]:
    """Parse only named source columns; ambiguous/invalid values remain in RAW.

    This never coalesces duplicate terms or selects a scoring observation.
    """
    values: dict[str, int | Decimal | None] = {}
    quality: dict[str, object] = {"source_columns": {}, "parse_errors": []}
    for column, label in header_cells.items():
        target = MARKET_HEADERS.get(" ".join(str(label).strip().casefold().split()))
        if target is None:
            continue
        if target in values:
            quality["parse_errors"].append("DUPLICATE_METRIC_HEADER")
            values[target] = None
            continue
        quality["source_columns"][target] = column
        raw = str(source_cells.get(column, "")).strip().replace(",", "").removeprefix("$")
        if not raw:
            values[target] = None
            continue
        try:
            number = Decimal(raw)
            if not number.is_finite() or number < 0 or number > Decimal("999999999999"):
                raise InvalidOperation
            if target in ("monthly_searches", "monthly_purchases"):
                if number != number.to_integral_value():
                    raise InvalidOperation
                values[target] = int(number)
            else:
                values[target] = number
        except InvalidOperation:
            values[target] = None
            quality["parse_errors"].append(f"{target.upper()}_INVALID")
    return values, quality


class PrivateBlobStore(Protocol):
    def put_immutable(self, *, account: str, upload_id: UUID, blob: bytes, sha256: str) -> str: ...


class PrivateLocalKeywordStore:
    """Explicitly configured LOCAL private directory; never a web-served folder."""

    def __init__(self, root: Path):
        if not root.is_absolute() or not root.exists() or not root.is_dir() or root.is_symlink():
            raise ValueError("PRIVATE_UPLOAD_ROOT_INVALID")
        if root.stat().st_mode & 0o077:
            raise ValueError("PRIVATE_UPLOAD_ROOT_PERMISSIONS_UNSAFE")
        self.root = root.resolve(strict=True)

    def put_immutable(self, *, account: str, upload_id: UUID, blob: bytes, sha256: str) -> str:
        import hashlib

        if hashlib.sha256(blob).hexdigest() != sha256:
            raise ValueError("ORIGINAL_BLOB_HASH_MISMATCH")
        # Do not put account names or caller-supplied filenames in filesystem paths.
        suffix = f"{upload_id.hex}-{sha256}.xlsx"
        target = self.root / suffix
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(blob)
                out.flush()
                os.fsync(out.fileno())
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return f"private-keyword://{suffix}"


def persist_original_keyword_upload(
    session: Session,
    *,
    account: str,
    product_id: UUID,
    filename: str,
    actor: str,
    raw_blob: bytes,
    store: PrivateBlobStore,
) -> tuple[UUID, str, int]:
    """One new upload row per call, even for identical file hashes.

    Object-store upload happens first (an orphan can be cleaned asynchronously if
    DB transaction rolls back). No update/delete of old source rows.
    """
    if not account or len(account) > 128 or not actor or len(actor) > 255:
        raise ValueError("INVALID_SOURCE_ACTOR")
    if not filename or len(filename) > 255 or "/" in filename or "\\" in filename:
        raise ValueError("ORIGINAL_FILENAME_INVALID")
    parsed: ParsedWorkbook = parse_keyword_xlsx(raw_blob)
    upload_id = uuid4()
    key = store.put_immutable(
        account=account, upload_id=upload_id, blob=raw_blob, sha256=parsed.sha256
    )
    valid_rows = [r for r in parsed.rows if r.keyword_normalized and not r.parse_errors]
    has_errors = any(
        r.parse_errors and r.parse_errors not in (("HEADER_ROW",), ("NON_KEYWORD_SHEET",))
        for r in parsed.rows
    )
    status = "failed" if has_errors or not valid_rows else "parsed"
    with session.begin():
        parent = RawKwUploadFile(
            id=upload_id,
            source_account_ref=account,
            product_id=product_id,
            original_filename=filename,
            object_key=key,
            mime_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            sha256=parsed.sha256,
            file_size_bytes=parsed.file_size_bytes,
            parser_version=parsed.parser_version,
            status=status,
            uploaded_by=actor,
            error_code="KW_SOURCE_ROWS_INVALID" if status == "failed" else None,
        )
        session.add(parent)
        source_rows = []
        for raw in parsed.rows:
            entry = RawKwUploadRow(
                id=uuid4(),
                upload_id=upload_id,
                source_account_ref=account,
                sheet_name=raw.sheet_name,
                row_number=raw.row_number,
                source_cells=raw.source_cells,
                keyword_raw=raw.keyword_raw,
                keyword_normalized=raw.keyword_normalized,
                parse_errors=list(raw.parse_errors),
            )
            session.add(entry)
            source_rows.append(entry)
        session.flush()
        if status == "parsed":
            headers = {
                row.sheet_name: row.source_cells
                for row in source_rows
                if row.parse_errors == ["HEADER_ROW"]
            }
            unique = {}
            for raw in source_rows:
                if raw.keyword_normalized and not raw.parse_errors:
                    unique.setdefault(raw.keyword_normalized, raw.keyword_raw)
            for normalized, canonical in unique.items():
                session.execute(
                    pg_insert(DimKwTerm)
                    .values(
                        id=uuid4(),
                        canonical_keyword=canonical,
                        normalized_keyword=normalized,
                        normalization_version=NORMALIZER_VERSION,
                    )
                    .on_conflict_do_nothing(index_elements=["normalized_keyword"])
                )
            terms = {
                term.normalized_keyword: term
                for term in session.scalars(
                    select(DimKwTerm).where(DimKwTerm.normalized_keyword.in_(unique))
                )
            }
            if set(terms) != set(unique):
                raise ValueError("VOCABULARY_UPSERT_INCOMPLETE")
            for raw in source_rows:
                if raw.keyword_normalized is None or raw.parse_errors:
                    continue
                term = terms[raw.keyword_normalized]
                session.execute(
                    pg_insert(BizSkuKeyword)
                    .values(
                        id=uuid4(),
                        source_account_ref=account,
                        product_id=product_id,
                        term_id=term.id,
                        status="review",
                    )
                    .on_conflict_do_nothing(index_elements=["product_id", "term_id"])
                )
                session.add(
                    BizKwSourceEvent(
                        id=uuid4(),
                        source_account_ref=account,
                        product_id=product_id,
                        term_id=term.id,
                        source_kind="excel",
                        source_event_key=f"upload:{upload_id.hex}:{raw.id.hex}",
                        source_reference=key,
                        store_id=None,
                        evidence_json={
                            "upload_id": str(upload_id),
                            "raw_row_id": str(raw.id),
                            "sheet": raw.sheet_name,
                            "row": raw.row_number,
                        },
                        discovered_at=datetime.now(UTC),
                    )
                )
                metrics, quality = market_observation_from_row(
                    headers.get(raw.sheet_name, {}),
                    raw.source_cells,
                )
                if metrics:
                    session.add(
                        BizKwMarketObservation(
                            id=uuid4(),
                            source_account_ref=account,
                            product_id=product_id,
                            term_id=term.id,
                            upload_row_id=raw.id,
                            source_kind="excel",
                            observed_date=None,
                            monthly_searches=metrics.get("monthly_searches"),
                            monthly_purchases=metrics.get("monthly_purchases"),
                            ppc_usd=metrics.get("ppc_usd"),
                            bid_min_usd=metrics.get("bid_min_usd"),
                            bid_max_usd=metrics.get("bid_max_usd"),
                            source_metrics_json=quality,
                        )
                    )
            # Existing SKU keywords must never belong to a different account.
            session.flush()
            scoped_keywords = list(
                session.scalars(
                    select(BizSkuKeyword).where(
                        BizSkuKeyword.product_id == product_id,
                        BizSkuKeyword.term_id.in_([row.id for row in terms.values()]),
                    )
                )
            )
            if any(row.source_account_ref != account for row in scoped_keywords):
                raise ValueError("EXISTING_KEYWORD_ACCOUNT_CONFLICT")
    return upload_id, status, len(parsed.rows)
