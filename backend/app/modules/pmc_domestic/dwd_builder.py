"""Receipt ODS → domestic batch DWD rows (phase 1)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from app.modules.pmc_domestic.dates import receive_time_to_taipei_business_date
from app.modules.pmc_purchase.dwd_builder import latest_versions

DWD_BUILDER_VERSION = "pmc_domestic.dwd_builder.v1"


class OdsRowLike(Protocol):
    id: UUID
    run_id: UUID
    raw_request_ref_id: UUID
    source_account_ref: str
    payload_json: dict[str, object]
    observed_at: datetime


class OdsReceiptLike(OdsRowLike, Protocol):
    order_sn: str
    business_order_sn: str | None
    receive_time: str | None
    update_time: str | None
    wid: str | None


class OdsReceiptItemLike(OdsRowLike, Protocol):
    receipt_order_sn: str
    line_ordinal: int
    sku: str | None
    product_receive_num: int | None


@dataclass(frozen=True, slots=True)
class SourceRef:
    ods_id: UUID
    run_id: UUID
    raw_request_ref_id: UUID
    observed_at: datetime
    provider_update_time: str | None


@dataclass(frozen=True, slots=True)
class ReceiptBatchRow:
    source_account_ref: str
    receipt_order_sn: str
    line_ordinal: int
    purchase_order_sn: str | None
    source_warehouse_id: str | None
    sku: str | None
    received_qty: int | None
    receive_time: str | None
    received_business_date: date | None
    source: SourceRef


@dataclass(frozen=True, slots=True)
class DwdBuildReport:
    receipts_seen: int
    receipts_kept: int
    receipts_superseded: int
    lines_kept: int


def _source(row: OdsRowLike, provider_update_time: str | None) -> SourceRef:
    return SourceRef(
        ods_id=row.id,
        run_id=row.run_id,
        raw_request_ref_id=row.raw_request_ref_id,
        observed_at=row.observed_at,
        provider_update_time=provider_update_time,
    )


def _clean_id(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def build_receipt_batches(
    ods_receipts: Sequence[OdsReceiptLike],
    ods_receipt_items: Sequence[OdsReceiptItemLike],
) -> tuple[list[ReceiptBatchRow], DwdBuildReport]:
    chosen, superseded = latest_versions(ods_receipts, lambda r: r.order_sn)
    chosen_runs = {
        (receipt.source_account_ref, receipt.order_sn): receipt.run_id
        for receipt in chosen.values()
    }
    rows: list[ReceiptBatchRow] = []
    for item in sorted(
        ods_receipt_items,
        key=lambda r: (r.source_account_ref, r.receipt_order_sn, r.line_ordinal),
    ):
        header_key = (item.source_account_ref, item.receipt_order_sn)
        if chosen_runs.get(header_key) != item.run_id:
            continue
        receipt = chosen[header_key]
        provider_update = receipt.update_time or (
            str(receipt.payload_json.get("update_time"))
            if isinstance(receipt.payload_json.get("update_time"), str | int)
            else None
        )
        receive_time = receipt.receive_time
        rows.append(
            ReceiptBatchRow(
                source_account_ref=item.source_account_ref,
                receipt_order_sn=item.receipt_order_sn,
                line_ordinal=item.line_ordinal,
                purchase_order_sn=_clean_id(receipt.business_order_sn),
                source_warehouse_id=_clean_id(receipt.wid),
                sku=_clean_id(item.sku),
                received_qty=item.product_receive_num,
                receive_time=receive_time,
                received_business_date=receive_time_to_taipei_business_date(receive_time),
                source=_source(item, provider_update),
            )
        )
    return rows, DwdBuildReport(
        receipts_seen=len(ods_receipts),
        receipts_kept=len(chosen),
        receipts_superseded=superseded,
        lines_kept=len(rows),
    )
