"""Build per-store GTIN input for the original Walmart inventory-log collector.

Source is a provisioned local CSV, not a caller-controlled path. Never log rows.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class GtinSourceRejected(ValueError):
    """Non-sensitive validation failure."""


def build_gtin_input(*, store_code: str, store_id: str, directory: Path) -> Path:
    """Produce store_id,item_id,gtin CSV; preserve empty GTIN for worker fallback."""
    try:
        mapping = json.loads(os.getenv("SZZSBJ_WALMART_GTIN_SOURCES", "{}"))
    except (TypeError, ValueError):
        raise GtinSourceRejected("GTIN_MAPPING_INVALID") from None
    if not isinstance(mapping, dict):
        raise GtinSourceRejected("GTIN_MAPPING_INVALID")
    location = mapping.get(store_code)
    if not isinstance(location, str) or not location.startswith("/opt/szzsbj/walmart/gtin/"):
        raise GtinSourceRejected("GTIN_SOURCE_UNCONFIGURED")
    source = Path(location)
    approved = Path("/opt/szzsbj/walmart/gtin")
    if not source.resolve().is_relative_to(approved.resolve()):
        raise GtinSourceRejected("GTIN_SOURCE_INVALID")
    if source.suffix.lower() != ".csv" or source.is_symlink() or not source.is_file():
        raise GtinSourceRejected("GTIN_SOURCE_INVALID")
    if source.stat().st_size > 20 * 1024 * 1024:
        raise GtinSourceRejected("GTIN_SOURCE_TOO_LARGE")
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise GtinSourceRejected("GTIN_OUTPUT_INVALID")
    output = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        prefix="gtins-",
        suffix=".csv",
        dir=directory,
        delete=False,
    )
    try:
        with output as handle, source.open(encoding="utf-8-sig", newline="") as incoming:
            reader = csv.DictReader(incoming)
            headers = reader.fieldnames or []
            if "gtin" not in headers or "item_id" not in headers:
                raise GtinSourceRejected("GTIN_COLUMNS_INVALID")
            writer = csv.writer(handle)
            writer.writerow(("store_id", "item_id", "gtin"))
            count = 0
            for row in reader:
                if row.get("store_id") not in (None, "", store_id):
                    raise GtinSourceRejected("GTIN_STORE_MISMATCH")
                gtin = (row.get("gtin") or "").strip()
                item_id = (row.get("item_id") or "").strip()
                if len(gtin) > 64 or len(item_id) > 64:
                    raise GtinSourceRejected("GTIN_VALUE_INVALID")
                writer.writerow((store_id, item_id, gtin))
                count += 1
                if count > 100000:
                    raise GtinSourceRejected("GTIN_ROW_LIMIT")
            if count == 0:
                raise GtinSourceRejected("GTIN_SOURCE_EMPTY")
        return Path(output.name)
    except Exception:
        Path(output.name).unlink(missing_ok=True)
        raise


def build_system_gtin_input(
    *, session: "Session", source_account_ref: str, store_id: str, directory: Path
) -> Path:
    """Create worker input from the authoritative scoped listing dimension.

    Do not silently mix data from different source accounts or stores.
    Empty GTIN is retained for the original worker fallback behavior.
    """
    from sqlalchemy import select

    from app.modules.data_pages.models import WalmartListingDimension

    if not store_id.isdecimal() or not source_account_ref:
        raise GtinSourceRejected("GTIN_STORE_INVALID")
    rows = session.execute(
        select(
            WalmartListingDimension.item_id,
            WalmartListingDimension.gtin,
        )
        .where(
            WalmartListingDimension.source_account_ref == source_account_ref,
            WalmartListingDimension.store_id == store_id,
            WalmartListingDimension.platform_code == "walmart",
        )
        .order_by(WalmartListingDimension.item_id)
        .limit(100001)
    ).all()
    if not rows:
        raise GtinSourceRejected("GTIN_SYSTEM_SOURCE_EMPTY")
    if len(rows) > 100000:
        raise GtinSourceRejected("GTIN_ROW_LIMIT")
    if directory.is_symlink():
        raise GtinSourceRejected("GTIN_OUTPUT_INVALID")
    directory.mkdir(parents=True, exist_ok=True)
    output = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", prefix="gtins-", suffix=".csv",
        dir=directory, delete=False,
    )
    try:
        with output as handle:
            writer = csv.writer(handle)
            writer.writerow(("store_id", "item_id", "gtin"))
            for item_id, gtin in rows:
                if not item_id or len(item_id) > 64 or len(gtin or "") > 64:
                    raise GtinSourceRejected("GTIN_VALUE_INVALID")
                writer.writerow((store_id, item_id, (gtin or "").strip()))
        return Path(output.name)
    except Exception:
        Path(output.name).unlink(missing_ok=True)
        raise
