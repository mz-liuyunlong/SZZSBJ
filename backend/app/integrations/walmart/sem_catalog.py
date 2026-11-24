"""Walmart Sponsored Search (SEM, ``/v3/advertising/sem``) contracts.

Reads: 3 GETs plus 5 POST queries (report-style lookups with filters in the body; they
change nothing, so they are in ``READ_SEMANTIC_NON_GET_KEYS``). The POST query bodies are
objects restricted to the documented filter / paging keys.

Writes (owner authorization 2026-11-24, real write test passed 2026-10-11): create / update /
stop / delete a campaign. They stay behind the same gate as the WFS writes: read-write live
mode, ``MAX_RISK=write``, the key listed in the approved write keys, an ``approval_ref`` and a
shared replay store. Campaign create / update bodies are documented objects; we restrict the
top-level keys to the documented campaign fields.
"""

from __future__ import annotations

from app.integrations.walmart._catalog_base import enabled_registry
from app.integrations.walmart.contracts import ContractRegistry, Field, Operation

_DOC = "https://developer.walmart.com/us-marketplace/docs/"
_PAGING = {
    "limit": {"type": "integer"},
    "offset": {"type": "integer"},
    "pageNumber": {"type": "integer"},
    "pageSize": {"type": "integer"},
    "cursor": {"type": "string"},
}
_DATE_RANGE = {
    "startDate": {"type": "string", "maxLength": 32},
    "endDate": {"type": "string", "maxLength": 32},
    "dateRange": {"type": "string", "maxLength": 32},
}


def _query_body(**extra: object) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {**_PAGING, **_DATE_RANGE, **extra},
        "additionalProperties": False,
    }


_ID_LIST = {"type": "array", "items": {"type": "string"}, "maxItems": 1000}

READ_OPERATIONS = (
    Operation(
        key="sem_campaign_get",
        method="GET",
        path="/v3/advertising/sem/campaigns/{campaignId}",
        fields=(Field("campaignId", "path", required=True),),
        source=_DOC + "get-campaign-details",
    ),
    Operation(
        key="sem_items_recommendations",
        method="GET",
        path="/v3/advertising/sem/items/recommendations",
        fields=(Field("limit", "query", kind="integer", maximum=200),),
        source=_DOC + "get-top-recommended-items-from-your-catalog",
    ),
    Operation(
        key="sem_item_issue_types",
        method="GET",
        path="/v3/advertising/sem/item-issues/issue-types",
        fields=(),
        source=_DOC + "get-issue-types",
    ),
    Operation(
        key="sem_billing_history",
        method="POST",
        path="/v3/advertising/sem/billing-history",
        fields=(),
        has_body=True,
        body_required=True,
        request_schema=_query_body(),
        mutating=False,
        source=_DOC + "get-billing-history",
    ),
    Operation(
        key="sem_campaigns_performance_summary",
        method="POST",
        path="/v3/advertising/sem/campaigns/performance-summary",
        fields=(),
        has_body=True,
        body_required=True,
        request_schema=_query_body(campaignIds=_ID_LIST, status={"type": "string"}),
        mutating=False,
        source=_DOC + "get-campaign-performance-summary",
    ),
    Operation(
        key="sem_item_level_summary",
        method="POST",
        path="/v3/advertising/sem/campaigns/{campaignId}/item-level-summary",
        fields=(Field("campaignId", "path", required=True),),
        has_body=True,
        body_required=True,
        request_schema=_query_body(skus=_ID_LIST, itemIds=_ID_LIST),
        mutating=False,
        source=_DOC + "get-item-level-summary",
    ),
    Operation(
        key="sem_item_issues_search",
        method="POST",
        path="/v3/advertising/sem/item-issues/search",
        fields=(),
        has_body=True,
        body_required=True,
        request_schema=_query_body(
            skus=_ID_LIST, itemIds=_ID_LIST, issueTypes=_ID_LIST, campaignIds=_ID_LIST
        ),
        mutating=False,
        source=_DOC + "search-item-issues",
    ),
    Operation(
        key="sem_items_eligibility",
        method="POST",
        path="/v3/advertising/sem/items/eligibility",
        fields=(),
        has_body=True,
        body_required=True,
        request_schema=_query_body(skus=_ID_LIST, itemIds=_ID_LIST),
        mutating=False,
        source=_DOC + "check-item-eligibility",
    ),
)

SEM_READ_KEYS: frozenset[str] = frozenset(operation.key for operation in READ_OPERATIONS)
SEM_READ_SEMANTIC_POST_KEYS: frozenset[str] = frozenset(
    operation.key for operation in READ_OPERATIONS if operation.method == "POST"
)

CAMPAIGN_BODY_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "campaignName": {"type": "string", "maxLength": 255},
        "campaignType": {"type": "string", "maxLength": 64},
        "targetingType": {"type": "string", "maxLength": 64},
        "status": {"type": "string", "maxLength": 32},
        "startDate": {"type": "string", "maxLength": 32},
        "endDate": {"type": "string", "maxLength": 32},
        "dailyBudget": {"type": "number"},
        "totalBudget": {"type": "number"},
        "budgetType": {"type": "string", "maxLength": 32},
        "biddingStrategy": {"type": "string", "maxLength": 64},
        "adGroups": {"type": "array", "maxItems": 100},
        "items": {"type": "array", "maxItems": 1000},
        "keywords": {"type": "array", "maxItems": 1000},
        "placements": {"type": "array", "maxItems": 20},
        "bidMultipliers": {"type": "object"},
    },
    "additionalProperties": False,
}

WRITE_OPERATIONS = (
    Operation(
        key="sem_campaign_create",
        method="POST",
        path="/v3/advertising/sem/campaigns",
        fields=(),
        has_body=True,
        body_required=True,
        request_schema=CAMPAIGN_BODY_SCHEMA,
        mutating=True,
        source=_DOC + "create-a-campaign",
    ),
    Operation(
        key="sem_campaign_update",
        method="PUT",
        path="/v3/advertising/sem/campaigns/{campaignId}",
        fields=(Field("campaignId", "path", required=True),),
        has_body=True,
        body_required=True,
        request_schema=CAMPAIGN_BODY_SCHEMA,
        mutating=True,
        source=_DOC + "update-a-campaign",
    ),
    Operation(
        key="sem_campaign_stop",
        method="PUT",
        path="/v3/advertising/sem/campaigns/{campaignId}/stop",
        fields=(Field("campaignId", "path", required=True),),
        mutating=True,
        source=_DOC + "stop-a-campaign",
    ),
    Operation(
        key="sem_campaign_delete",
        method="DELETE",
        path="/v3/advertising/sem/campaigns/{campaignId}",
        fields=(Field("campaignId", "path", required=True),),
        mutating=True,
        source=_DOC + "delete-a-campaign",
    ),
)
SEM_WRITE_KEYS: frozenset[str] = frozenset(operation.key for operation in WRITE_OPERATIONS)
SEM_WRITE_PERMISSION = "action:walmart:sem:campaigns:write"


def sem_read_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    return enabled_registry(READ_OPERATIONS, approved_keys)


def sem_write_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    return enabled_registry(WRITE_OPERATIONS, approved_keys)
