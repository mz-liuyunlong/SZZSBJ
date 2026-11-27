"""US Marketplace on-request reports: create a request (read-semantic POST) and fetch the ZIP.

Owner authorization 2026-11-24 (business owner, 13:46 / 14:00): the cloud lane may create
report requests for the report types probed in 2026-10-11 and bring the generated ZIP back.

Flow (three contracts, all against marketplace.walmartapis.com):
1. ``report_request_create``  POST /v3/reports/reportRequests?reportType=&reportVersion=v1
   body: an object with optional ``dataStartTime`` / ``dataEndTime`` (ISO-8601 UTC) and
   nothing else; send ``{}`` to let Walmart use its default window (body is required so the
   read-only transport always sees an object).
   It creates a *report request* on Walmart's side and changes no seller data, so it is
   listed in ``READ_SEMANTIC_NON_GET_KEYS``; the body schema pins the two filter keys.
2. ``report_request_status_get`` (operations_catalog)  GET /v3/reports/reportRequests/{id}
3. ``report_download``  GET /v3/reports/downloadReport?requestId=
   Walmart answers JSON with a ``downloadURL``; the transport follows it only when the URL
   is https on the same host and under ``/v3/``, and returns the ZIP bytes base64-encoded
   (``response_kind="zip"``, size-capped). No other host, no redirects.
"""

from __future__ import annotations

from app.integrations.walmart.contracts import ContractError, ContractRegistry, Field, Operation

REPORT_REQUEST_CREATE_KEY = "report_request_create"
REPORT_DOWNLOAD_KEY = "report_download"

# Probed OK (or OK-but-empty) on 2026-10-11 through the old lane; everything else is not
# accepted until it has been probed once (catalog status PROBED_ERROR / UNVERIFIED).
REPORT_TYPES: tuple[str, ...] = (
    "SETTLEMENT",
    "WFS_STORAGE_FEE",
    "WFS_CUSTOMER_RETURNS",
    "WFS_ORDERS",
    "WFS_INVENTORY_HEALTH",
    "WFS_INVENTORY_LOG",
    "INVENTORY_RECON",
    "DISCOUNT",
    "CPA",
    "ITEM",
    "INVENTORY",
    "PROMO",
    "BUYBOX",
    "ITEM_PERFORMANCE",
    "LISTING_QUALITY",
    "CONTENT_QUALITY",
    "INVENTORY_RECOMMENDATIONS",
    "SEARCH_INSIGHTS_PERF_REPORT",
    "SEARCH_INSIGHTS_SQR_REPORT",
    "SEM_PERFORMANCE",
    "SEM_SEARCH_TERMS",
    "SQR",
    "LAGTIME",
    "lagtime",
)

REPORT_REQUEST_BODY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "dataStartTime": {"type": "string", "maxLength": 32},
        "dataEndTime": {"type": "string", "maxLength": 32},
    },
    "additionalProperties": False,
}

_OPERATIONS = (
    Operation(
        key=REPORT_REQUEST_CREATE_KEY,
        method="POST",
        path="/v3/reports/reportRequests",
        fields=(
            Field("reportType", "query", required=True, enum=REPORT_TYPES),
            Field("reportVersion", "query", required=True, enum=("v1",)),
        ),
        has_body=True,
        body_required=True,
        request_schema=REPORT_REQUEST_BODY_SCHEMA,
        mutating=False,
        source="https://developer.walmart.com/us-marketplace/docs/request-a-settlement-report",
    ),
    Operation(
        key=REPORT_DOWNLOAD_KEY,
        method="GET",
        path="/v3/reports/downloadReport",
        fields=(Field("requestId", "query", required=True),),
        response_kind="zip",
        source="https://developer.walmart.com/us-marketplace/docs/request-a-settlement-report",
    ),
)


def reports_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
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
                mutating=operation.mutating,
                response_kind=operation.response_kind,
            )
            for operation in _OPERATIONS
        )
    )
