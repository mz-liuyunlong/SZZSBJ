"""US Marketplace settlement (reconciliation) report read contracts for finance.

Only the two GET operations finance needs to reconcile Walmart payouts are included:
list the available v1 recon report dates, and page through one report as JSON.
The zip / CSV download (``/v3/report/reconreport/reconFile``) is deliberately excluded:
the protected transport only returns JSON or PDF bodies. Both operations were run
read-only on 2026-11-03 from the local draft; this file registers them in the repo so
the payout-reconciliation sync (finance) can call them through the cloud lane.
"""

from __future__ import annotations

from app.integrations.walmart.contracts import ContractError, ContractRegistry, Field, Operation

RECON_MAX_RECORDS = 1000

_OPERATIONS = (
    Operation(
        key="recon_report_dates",
        method="GET",
        path="/v3/report/reconreport/availableReconFiles",
        fields=(Field("reportVersion", "query", required=True, enum=("v1",)),),
        source="https://developer.walmart.com/us-marketplace/docs/available-recon-report-dates",
    ),
    Operation(
        key="recon_report_json",
        method="GET",
        path="/v3/report/reconreport/reconFileJson",
        fields=(
            Field("reportDate", "query", required=True),
            Field("offset", "query", required=True, kind="integer"),
            Field("noOfRecords", "query", required=True, kind="integer", maximum=RECON_MAX_RECORDS),
        ),
        source=(
            "https://developer.walmart.com/us-marketplace/reference/"
            "getavailablev1reconreportasjson-1"
        ),
    ),
)


def recon_read_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    known = frozenset(operation.key for operation in _OPERATIONS)
    if approved_keys - known:
        raise ContractError("WALMART_APPROVED_OPERATION_UNKNOWN")
    return ContractRegistry(
        tuple(
            Operation(
                key=operation.key,
                method=operation.method,
                path=operation.path,
                fields=operation.fields,
                has_body=operation.has_body,
                source=operation.source,
                enabled=operation.key in approved_keys,
                request_schema=operation.request_schema,
                request_content_type=operation.request_content_type,
                body_required=operation.body_required,
                media_supported=operation.media_supported,
            )
            for operation in _OPERATIONS
        )
    )
