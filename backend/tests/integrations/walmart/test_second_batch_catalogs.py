"""2026-11-24 second batch: reports (create + ZIP), payment, insights, SEM, misc, growth POSTs.

Checks the shape every contract must have, that the read-semantic POST set equals exactly
the non-GET read contracts in the reviewed registry, and that writes stay writes.
"""

from __future__ import annotations

import pytest

from app.integrations.walmart.contract_signing import READ_SEMANTIC_NON_GET_KEYS, risk_for
from app.integrations.walmart.contracts import ContractError
from app.integrations.walmart.growth_catalog import growth_read_registry
from app.integrations.walmart.insights_catalog import insights_read_registry
from app.integrations.walmart.misc_catalog import misc_read_registry
from app.integrations.walmart.payment_catalog import payment_read_registry
from app.integrations.walmart.reports_catalog import REPORT_TYPES, reports_registry
from app.integrations.walmart.sem_catalog import (
    SEM_READ_KEYS,
    SEM_WRITE_KEYS,
    SEM_WRITE_PERMISSION,
    sem_read_registry,
    sem_write_registry,
)
from app.integrations.walmart.unified_api import (
    ALL_WRITE_KEYS,
    load_unified_registry,
    reviewed_registry,
)
from app.integrations.walmart.wfs_write_catalog import WFS_WRITE_KEYS


def test_report_request_create_is_a_pinned_read_semantic_post() -> None:
    registry = reports_registry(approved_keys=frozenset({"report_request_create"}))
    request = registry.prepare(
        "report_request_create",
        params={"reportType": "SETTLEMENT", "reportVersion": "v1"},
        body={"dataStartTime": "2026-10-01T00:00:00Z", "dataEndTime": "2026-10-31T23:59:59Z"},
    )
    assert (request.method, request.path) == ("POST", "/v3/reports/reportRequests")
    assert request.is_write is False and risk_for("POST", "report_request_create") == "read"
    # body optional (Walmart defaults the window), but only the two documented keys
    assert (
        registry.prepare(
            "report_request_create", params={"reportType": "ITEM", "reportVersion": "v1"}
        ).body
        is None
    )
    with pytest.raises(ContractError, match="WALMART_BODY_FIELD_NOT_ALLOWED"):
        registry.prepare(
            "report_request_create",
            params={"reportType": "ITEM", "reportVersion": "v1"},
            body={"reportType": "SETTLEMENT"},
        )
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        registry.prepare(
            "report_request_create", params={"reportType": "SALES", "reportVersion": "v1"}
        )
    with pytest.raises(ContractError, match="WALMART_PARAM_REQUIRED"):
        registry.prepare("report_request_create", params={"reportType": "ITEM"})
    assert "RETURN_ITEM_OVERRIDES" not in REPORT_TYPES and "SETTLEMENT" in REPORT_TYPES


def test_report_download_is_a_get_with_zip_response() -> None:
    registry = reports_registry(approved_keys=frozenset({"report_download"}))
    request = registry.prepare("report_download", params={"requestId": "abc-123"})
    assert (request.method, request.response_kind, request.is_write) == ("GET", "zip", False)
    assert dict(request.query) == {"requestId": "abc-123"}


def test_payment_insights_misc_are_get_only_with_documented_params() -> None:
    payment = payment_read_registry(approved_keys=frozenset({"payment_statement"}))
    assert payment.prepare("payment_statement").path == "/v3/report/payment/statement"
    with pytest.raises(ContractError, match="WALMART_PARAM_NOT_ALLOWED"):
        payment.prepare("payment_statement", params={"cycle": "x"})
    insights = insights_read_registry(
        approved_keys=frozenset({"insights_unpublished_items", "insights_listing_quality_items"})
    )
    page = insights.prepare(
        "insights_unpublished_items",
        params={"fromDate": "2026-10-01", "unpublishedReasonCode": "NO_PRICE", "limit": 100},
    )
    assert page.method == "GET" and page.query["unpublishedReasonCode"] == "NO_PRICE"
    with pytest.raises(ContractError, match="WALMART_FIELD_INVALID"):
        insights.prepare("insights_unpublished_items", params={"unpublishedReasonCode": "OTHER"})
    query = insights.prepare("insights_listing_quality_items", body={"wfsFlag": True, "limit": 50})
    assert query.method == "POST" and query.is_write is False
    with pytest.raises(ContractError, match="WALMART_BODY_FIELD_NOT_ALLOWED"):
        insights.prepare("insights_listing_quality_items", body={"sql": "drop"})
    misc = misc_read_registry(approved_keys=frozenset({"lagtime_get", "shipping_template_get"}))
    assert misc.prepare("lagtime_get", params={"sku": "A/B"}).query == {"sku": "A/B"}
    assert (
        misc.prepare("shipping_template_get", params={"templateId": "t 1"}).path
        == "/v3/settings/shipping/templates/t%201"
    )
    for registry in (payment, insights, misc):
        assert all(not registry.get(key).is_write for key in registry.keys())


def test_sem_reads_and_writes_are_separated() -> None:
    reads = sem_read_registry(approved_keys=SEM_READ_KEYS)
    assert all(not reads.get(key).is_write for key in reads.keys())
    summary = reads.prepare(
        "sem_campaigns_performance_summary",
        body={"startDate": "2026-10-01", "endDate": "2026-10-31", "campaignIds": ["1"]},
    )
    assert summary.method == "POST" and risk_for("POST", summary.key) == "read"
    with pytest.raises(ContractError, match="WALMART_BODY_FIELD_NOT_ALLOWED"):
        reads.prepare("sem_billing_history", body={"dailyBudget": 1})
    writes = sem_write_registry(approved_keys=SEM_WRITE_KEYS)
    assert all(writes.get(key).is_write for key in writes.keys())
    with pytest.raises(ContractError, match="WALMART_WRITE_NOT_AUTHORIZED"):
        writes.prepare("sem_campaign_stop", params={"campaignId": "1"})
    stop = writes.prepare("sem_campaign_stop", params={"campaignId": "1"}, allow_writes=True)
    assert stop.method == "PUT" and risk_for("PUT", "sem_campaign_stop") == "write"
    assert SEM_WRITE_KEYS.isdisjoint(READ_SEMANTIC_NON_GET_KEYS)
    assert SEM_WRITE_KEYS <= ALL_WRITE_KEYS and WFS_WRITE_KEYS <= ALL_WRITE_KEYS
    assert reviewed_registry().get("sem_campaign_create").permission == SEM_WRITE_PERMISSION
    assert reviewed_registry().get("sem_campaign_get").permission == "action:walmart:sem:read"


def test_read_semantic_set_matches_the_reviewed_non_get_reads_exactly() -> None:
    registry = reviewed_registry()
    non_get_reads = {
        key
        for key in registry.keys()
        if registry.get(key).method != "GET" and not registry.get(key).is_write
    }
    assert non_get_reads == READ_SEMANTIC_NON_GET_KEYS
    for key in non_get_reads:
        operation = registry.get(key)
        assert (
            operation.method == "POST"
            and operation.has_body
            and operation.body_required
            or (key == "report_request_create")
        )
        schema = operation.request_schema
        assert isinstance(schema, dict) and schema.get("additionalProperties") is False
        assert operation.risk == "read" == risk_for(operation.method, key)
    # a PUT / DELETE with a read-semantic key is still a write on the cloud side
    assert all(risk_for("PUT", key) == "write" for key in READ_SEMANTIC_NON_GET_KEYS)
    # growth family now has four read-semantic POSTs
    assert set(growth_read_registry().keys()) == {
        "review_accelerator_items",
        "review_accelerator_categories",
        "assortment_recommendations",
        "assortment_categorization_counts",
    }


def test_unified_registry_enables_only_what_is_approved() -> None:
    unified = load_unified_registry(
        frozenset({"payment_statement", "report_download"}),
        approved_write_keys=frozenset({"sem_campaign_stop"}),
    )
    assert unified.get("payment_statement").enabled and unified.get("report_download").enabled
    assert not unified.get("insights_listing_quality_score").enabled
    assert unified.get("sem_campaign_stop").enabled and unified.get("sem_campaign_stop").is_write
    with pytest.raises(Exception, match="WALMART_WRITE_NOT_AUTHORIZED"):
        load_unified_registry(frozenset({"sem_campaign_stop"}))
