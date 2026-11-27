"""US Marketplace payment reports (current cycle): statement and performance, both GET, no params.

Finance uses the statement's ``accountSummary`` (reserve / paidToYou / holdAmt) for payout
reconciliation. Historical cycles come from the recon catalog.
"""

from __future__ import annotations

from app.integrations.walmart._catalog_base import enabled_registry
from app.integrations.walmart.contracts import ContractRegistry, Operation

_DOC = "https://developer.walmart.com/us-marketplace/docs/"
_OPERATIONS = (
    Operation(
        key="payment_statement",
        method="GET",
        path="/v3/report/payment/statement",
        fields=(),
        source=_DOC + "payment-statement-report",
    ),
    Operation(
        key="payment_performance",
        method="GET",
        path="/v3/report/payment/performance",
        fields=(),
        source=_DOC + "performance-report",
    ),
)


def payment_read_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    return enabled_registry(_OPERATIONS, approved_keys)
