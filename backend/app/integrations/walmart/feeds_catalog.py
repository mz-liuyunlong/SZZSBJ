"""Reviewed read-only Walmart US feed monitoring contracts.

Official references:
https://developer.walmart.com/us-marketplace/reference/getallfeedstatuses
https://developer.walmart.com/us-marketplace/reference/getfeeditemstatus

Submitting feeds is a different, sensitive write workflow and is NOT enabled
by importing read-only monitoring operations.
"""

from __future__ import annotations

from app.integrations.walmart.contracts import ContractError, ContractRegistry, Field, Operation


def feed_monitor_registry(
    *, approved_keys: frozenset[str] = frozenset()
) -> ContractRegistry:
    """Return approved feed monitoring operations; default denies all outbound."""
    known = frozenset({"feed_status_list", "feed_item_status"})
    if approved_keys - known:
        raise ContractError("WALMART_APPROVED_OPERATION_UNKNOWN")

    # Feed type/status are response filters, not supported query parameters.
    pagination = (
        Field("limit", "query", kind="integer", maximum=50),
        Field("offset", "query", kind="integer"),
        Field("includeDetails", "query", kind="boolean"),
    )
    return ContractRegistry(
        (
            Operation(
                key="feed_status_list",
                method="GET",
                path="/v3/feeds",
                fields=(
                    Field("feedId", "query"),
                    *pagination,
                ),
                source="walmart-us-marketplace-feed-status-2026-10",
                enabled="feed_status_list" in approved_keys,
            ),
            Operation(
                key="feed_item_status",
                method="GET",
                path="/v3/feeds/{feedId}",
                fields=(
                    Field("feedId", "path", required=True),
                    *pagination,
                ),
                source="walmart-us-marketplace-feed-item-status-2026-10",
                enabled="feed_item_status" in approved_keys,
            ),
        )
    )
