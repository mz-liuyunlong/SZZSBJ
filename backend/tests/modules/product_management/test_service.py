from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.product_management.models import (
    ProductManagementPricingCurrent,
    ProductPricingRecalculationRun,
    ProductPricingRuleVersion,
)
from app.modules.product_management.schemas import (
    PricingRuleWrite,
    ProductManagementListQuery,
    ProductManagementSummaryQuery,
    RecalculatePricingRequest,
)
from app.modules.product_management.service import ProductManagementService
from app.modules.products.models import Product
from app.modules.sku_detail.models import (
    LingxingSkuGlobalTag,
    LingxingSkuIdentity,
    LingxingSkuProductInfoCurrent,
    SkuBaseProfileCurrent,
)

RULE_ID = UUID("00000000-0000-0000-0000-000000000010")
RUN_ID = UUID("00000000-0000-0000-0000-000000000011")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _pricing_rule_payload(**changes: object) -> PricingRuleWrite:
    values: dict[str, object] = {
        "source_account_ref": "synthetic-account",
        "version": "synthetic-v1",
        "effective_from": NOW,
        "wfs_source_url": ("https://marketplace.walmart.com/walmart-fulfillment-services-pricing/"),
        "wfs_confirmed_at": NOW,
        "wfs_confirmed_by": "synthetic-reviewer",
        "change_reason": "synthetic test",
        "approval_ref": "synthetic-approval",
    }
    values.update(changes)
    return PricingRuleWrite.model_validate(values)


def _rule(**changes: object) -> ProductPricingRuleVersion:
    values: dict[str, object] = {
        "id": RULE_ID,
        "source_account_ref": "synthetic-account",
        "version": "synthetic-v1",
        "effective_from": NOW,
        "effective_to": None,
        "is_active": True,
    }
    values.update(changes)
    return ProductPricingRuleVersion(**values)


def _recalculation_payload(**changes: object) -> RecalculatePricingRequest:
    values: dict[str, object] = {
        "source_account_ref": "synthetic-account",
        "scope": "all",
        "reason": "synthetic test",
        "idempotency_key": "synthetic-idempotency",
    }
    values.update(changes)
    return RecalculatePricingRequest.model_validate(values)


def _mutate(record: object, values: dict[str, object]) -> object:
    for name, value in values.items():
        setattr(record, name, value)
    return record


def test_product_core_manual_purchase_cost_precedes_synced_profile() -> None:
    product = Product(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        sku="SYNTHETIC-SKU",
        product_name="Synthetic Product",
        purchase_price=Decimal("9.00"),
        currency_code="USD",
    )
    profile = SkuBaseProfileCurrent(purchase_cost_cny=Decimal("12.00"))

    amount, source = ProductManagementService._purchase_cost_cny(product, profile, Decimal("7.00"))

    assert amount == Decimal("63.0000")
    assert source == "product_core_manual"


def test_synced_profile_is_used_when_manual_purchase_cost_is_absent() -> None:
    product = Product(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        sku="SYNTHETIC-SKU",
        product_name="Synthetic Product",
    )
    profile = SkuBaseProfileCurrent(purchase_cost_cny=Decimal("12.00"))

    amount, source = ProductManagementService._purchase_cost_cny(product, profile, None)

    assert amount == Decimal("12.00")
    assert source == "lingxing_profile"


def test_product_core_manual_grade_precedes_calculated_grade() -> None:
    identity = LingxingSkuIdentity(id=UUID("00000000-0000-0000-0000-000000000001"))
    product = Product(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        sku="SYNTHETIC-SKU",
        product_name="Synthetic Product",
        grade="B",
    )
    pricing = ProductManagementPricingCurrent(
        product_grade="C",
        grade_reason="calculated_grade_c",
        calculation_status="ok",
        calculated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    rule = ProductPricingRuleVersion(version="synthetic-v1")

    item = ProductManagementService._list_item(
        (identity, product, None, None, pricing, rule, None),
        [],
        0,
        include_costs=False,
    )

    assert item.product_grade == "B"
    assert item.grade_reason == "manual_product_grade"


def test_list_freshness_uses_oldest_returned_observation_and_reports_latest() -> None:
    session = MagicMock(spec=Session)
    service = ProductManagementService(session)
    service.repository = MagicMock()
    earlier = datetime(2026, 1, 1, tzinfo=UTC)
    later = datetime(2026, 1, 2, tzinfo=UTC)
    rows = [
        (
            LingxingSkuIdentity(id=UUID(int=index), last_seen_at=observed_at),
            Product(id=UUID(int=index + 10), sku=f"SYNTHETIC-{index}", product_name="Synthetic"),
            None,
            None,
            None,
            None,
            None,
        )
        for index, observed_at in ((1, later), (2, earlier))
    ]
    service.repository.list_projections.return_value = (rows, 2)
    service.repository.list_internal_tags.return_value = {}
    service.repository.list_source_tags_for_snapshots.return_value = {}
    service.repository.image_counts_for_snapshots.return_value = {}
    service.repository.list_effective_rules.return_value = {}
    service.repository.listing_counts.return_value = {}

    _, _, list_freshness_at, latest_observed_at = service.list_skus(
        ProductManagementListQuery(),
        frozenset({"synthetic-account"}),
        include_costs=False,
    )

    assert list_freshness_at == earlier
    assert latest_observed_at == later


def test_list_keeps_source_tags_separate_from_internal_tags() -> None:
    session = MagicMock(spec=Session)
    service = ProductManagementService(session)
    service.repository = MagicMock()
    identity = LingxingSkuIdentity(id=UUID(int=1), last_seen_at=NOW)
    current = LingxingSkuProductInfoCurrent(
        id=UUID(int=2),
        source_snapshot_id=UUID(int=3),
        source_observed_at=NOW,
        product_name="Synthetic Product",
    )
    source_tag = LingxingSkuGlobalTag(
        source_snapshot_id=current.source_snapshot_id,
        global_tag_id="synthetic-source-tag-id",
        tag_name="Synthetic Source Tag",
        color=None,
    )
    service.repository.list_projections.return_value = (
        [(identity, None, current, None, None, None, None)],
        1,
    )
    service.repository.list_internal_tags.return_value = {}
    service.repository.list_source_tags_for_snapshots.return_value = {
        current.source_snapshot_id: [source_tag]
    }
    service.repository.image_counts_for_snapshots.return_value = {}
    service.repository.list_effective_rules.return_value = {}
    service.repository.listing_counts.return_value = {}

    data, total, _, _ = service.list_skus(
        ProductManagementListQuery(),
        frozenset({"synthetic-account"}),
        include_costs=False,
    )

    assert total == 1
    assert data.items[0].internal_tags == []
    assert data.items[0].source_tags[0].label == "Synthetic Source Tag"


def test_summary_quantizes_repeating_completeness_rate() -> None:
    service = ProductManagementService(MagicMock(spec=Session))
    service.repository = MagicMock()
    service.repository.list_effective_rules.return_value = {}
    service.repository.summarize_projections.return_value = (
        3,
        3,
        Decimal("66.666666666666666667"),
        2,
        1,
        1,
        0,
        0,
        0,
        1,
        0,
        3,
    )

    result = service.summary(ProductManagementSummaryQuery(), frozenset({"synthetic-account"}))

    assert result.data_completeness_rate == Decimal("66.666667")


def test_recalculation_preview_does_not_write_projection_and_execute_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = SimpleNamespace()

    preview_session = MagicMock(spec=Session)
    preview = ProductManagementService(preview_session)
    preview.repository = MagicMock()
    preview.repository.get_recalculation_run.return_value = None
    preview.repository.get_effective_rule.return_value = _rule()
    preview.repository.list_recalculation_candidates.return_value = ([row], 1)
    preview.repository.update_record.side_effect = _mutate
    preview_calculation = MagicMock(return_value=0)
    monkeypatch.setattr(preview, "_recalculate_one", preview_calculation)

    preview_result = preview.recalculate(
        _recalculation_payload(),
        frozenset({"synthetic-account"}),
        actor_ref="synthetic-user",
        request_id="synthetic-preview-request",
    )

    assert preview_result.mode == "preview"
    assert preview_result.status == "previewed"
    assert preview_result.matched_count == 1
    assert preview_result.estimated_affected_count == 1
    assert preview_result.affected_count == 0
    preview_calculation.assert_not_called()
    preview_session.commit.assert_called_once_with()

    execute_session = MagicMock(spec=Session)
    execute = ProductManagementService(execute_session)
    execute.repository = MagicMock()
    execute.repository.get_recalculation_run.return_value = None
    execute.repository.get_effective_rule.return_value = _rule()
    execute.repository.list_recalculation_candidates.return_value = ([row], 1)
    execute.repository.update_record.side_effect = _mutate
    execute_calculation = MagicMock(return_value=0)
    monkeypatch.setattr(execute, "_recalculate_one", execute_calculation)

    execute_result = execute.recalculate(
        _recalculation_payload(preview_only=False),
        frozenset({"synthetic-account"}),
        actor_ref="synthetic-user",
        request_id="synthetic-execute-request",
    )

    assert execute_result.mode == "execute"
    assert execute_result.status == "succeeded"
    assert execute_result.affected_count == 1
    execute_calculation.assert_called_once()
    execute_session.commit.assert_called_once_with()


def test_zero_result_recalculation_still_persists_run() -> None:
    session = MagicMock(spec=Session)
    service = ProductManagementService(session)
    service.repository = MagicMock()
    service.repository.get_recalculation_run.return_value = None
    service.repository.get_effective_rule.return_value = _rule()
    service.repository.list_recalculation_candidates.return_value = ([], 0)
    service.repository.update_record.side_effect = _mutate

    result = service.recalculate(
        _recalculation_payload(),
        frozenset({"synthetic-account"}),
        actor_ref="synthetic-user",
        request_id="synthetic-zero-request",
    )

    run = service.repository.add_recalculation_run.call_args.args[0]
    assert result.status == "no_items"
    assert run.request_id == "synthetic-zero-request"
    assert run.actor_ref == "synthetic-user"
    assert run.source_account_ref == "synthetic-account"
    assert run.matched_count == 0
    assert run.finished_at is not None


def test_recalculation_replay_is_bound_to_digest_and_concurrent_unique_path() -> None:
    session = MagicMock(spec=Session)
    service = ProductManagementService(session)
    service.repository = MagicMock()
    payload = _recalculation_payload()
    digest = service._recalculation_request_digest(payload)
    replay = ProductPricingRecalculationRun(
        id=RUN_ID,
        principal_ref="synthetic-user",
        actor_ref="synthetic-user",
        source_account_ref="synthetic-account",
        request_digest=digest,
        request_id="synthetic-original-request",
        action="recalculate_pricing",
        page_key="product_management",
        capability="products:pricing:recalculate",
        mode="preview",
        status="previewed",
        scope="all",
        selected_count=0,
        matched_count=2,
        eligible_count=2,
        affected_count=0,
        skipped_count=0,
        failed_count=0,
        pricing_rule_version_id=RULE_ID,
        idempotency_key="synthetic-idempotency",
        error_code=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    service.repository.get_recalculation_run.return_value = replay

    result = service.recalculate(
        payload,
        frozenset({"synthetic-account"}),
        actor_ref="synthetic-user",
        request_id="synthetic-replay-request",
    )

    assert result.run_id == RUN_ID
    assert result.idempotent_replay is True
    service.repository.add_recalculation_run.assert_not_called()

    with pytest.raises(ApiError) as conflict:
        service.recalculate(
            _recalculation_payload(scope="selected", sku_ids=[UUID(int=99)]),
            frozenset({"synthetic-account"}),
            actor_ref="synthetic-user",
            request_id="synthetic-conflicting-request",
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"

    service.repository.get_recalculation_run.return_value = None
    service.repository.get_effective_rule.return_value = _rule()
    service.repository.list_recalculation_candidates.return_value = ([], 0)
    service.repository.update_record.side_effect = _mutate
    service.repository.add_recalculation_run.side_effect = IntegrityError(
        "synthetic unique conflict", {}, Exception()
    )
    service.repository.get_recalculation_run.side_effect = [None, replay]

    concurrent = service.recalculate(
        payload,
        frozenset({"synthetic-account"}),
        actor_ref="synthetic-user",
        request_id="synthetic-concurrent-request",
    )

    assert concurrent.idempotent_replay is True
    session.rollback.assert_called_once_with()


def test_data_scope_denied_recalculation_replay_stays_forbidden() -> None:
    session = MagicMock(spec=Session)
    service = ProductManagementService(session)
    service.repository = MagicMock()
    service.repository.get_recalculation_run.return_value = None
    service.repository.get_effective_rule.return_value = _rule()
    service.repository.list_recalculation_candidates.return_value = ([], 0)
    service.repository.update_record.side_effect = _mutate
    payload = _recalculation_payload(scope="selected", sku_ids=[UUID(int=99)])

    with pytest.raises(ApiError) as first:
        service.recalculate(
            payload,
            frozenset({"synthetic-account"}),
            actor_ref="synthetic-user",
            request_id="synthetic-denied-request",
        )
    assert first.value.status_code == 403
    assert first.value.code == "DATA_SCOPE_DENIED"

    failed_run = service.repository.add_recalculation_run.call_args.args[0]
    assert failed_run.status == "failed"
    service.repository.get_recalculation_run.return_value = failed_run
    with pytest.raises(ApiError) as replay:
        service.recalculate(
            payload,
            frozenset({"synthetic-account"}),
            actor_ref="synthetic-user",
            request_id="synthetic-denied-replay",
        )
    assert replay.value.status_code == 403
    assert replay.value.code == "DATA_SCOPE_DENIED"

    for error_code, status_code in (
        ("IDEMPOTENCY_CONFLICT", 409),
        ("INVALID_REQUEST", 422),
        ("VALIDATION_ERROR", 422),
    ):
        failed_run.error_code = error_code
        with pytest.raises(ApiError) as mapped:
            service.recalculate(
                payload,
                frozenset({"synthetic-account"}),
                actor_ref="synthetic-user",
                request_id="synthetic-failed-replay",
            )
        assert mapped.value.status_code == status_code
        assert mapped.value.code == error_code

    failed_run.error_code = "UNKNOWN_INTERNAL_RECALCULATION_DETAIL"
    with pytest.raises(ApiError) as unknown:
        service.recalculate(
            payload,
            frozenset({"synthetic-account"}),
            actor_ref="synthetic-user",
            request_id="synthetic-unknown-failed-replay",
        )
    assert unknown.value.status_code == 500
    assert unknown.value.code == "RECALCULATION_FAILED"


def test_recalculation_same_key_is_isolated_by_principal_source_and_mode() -> None:
    session = MagicMock(spec=Session)
    service = ProductManagementService(session)
    service.repository = MagicMock()
    service.repository.get_recalculation_run.return_value = None
    service.repository.get_effective_rule.return_value = _rule()
    service.repository.list_recalculation_candidates.return_value = ([], 0)
    service.repository.update_record.side_effect = _mutate

    service.recalculate(
        _recalculation_payload(),
        frozenset({"synthetic-account"}),
        actor_ref="synthetic-user-a",
        request_id="synthetic-a",
    )
    service.recalculate(
        _recalculation_payload(source_account_ref="synthetic-account-b", preview_only=False),
        frozenset({"synthetic-account-b"}),
        actor_ref="synthetic-user-b",
        request_id="synthetic-b",
    )

    first, second = [
        call.args[0] for call in service.repository.add_recalculation_run.call_args_list
    ]
    assert first.id != second.id
    assert first.principal_ref != second.principal_ref
    assert first.source_account_ref != second.source_account_ref
    assert first.mode == "preview"
    assert second.mode == "execute"


def test_pricing_rule_publish_closes_previous_open_version_and_records_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.modules.product_management.service._utc_now", lambda: NOW)
    session = MagicMock(spec=Session)
    service = ProductManagementService(session)
    service.repository = MagicMock()
    service.repository.update_record.side_effect = _mutate
    previous = _rule(version="synthetic-v1")
    service.repository.lock_rule_versions.return_value = [previous]
    next_start = datetime(2026, 2, 1, tzinfo=UTC)

    published = service.publish_rule(
        _pricing_rule_payload(version="synthetic-v2", effective_from=next_start),
        frozenset({"synthetic-account"}),
        actor_ref="synthetic-user",
        request_id="synthetic-rule-request",
    )

    assert previous.effective_to == next_start
    assert published.version == "synthetic-v2"
    assert published.request_id == "synthetic-rule-request"
    assert published.action == "publish_pricing_rule"
    assert published.status == "succeeded"
    session.commit.assert_called_once_with()


def test_pricing_rule_first_version_and_overlap_validation_are_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.modules.product_management.service._utc_now", lambda: NOW)
    session = MagicMock(spec=Session)
    service = ProductManagementService(session)
    service.repository = MagicMock()
    service.repository.lock_rule_versions.return_value = []

    published = service.publish_rule(
        _pricing_rule_payload(),
        frozenset({"synthetic-account"}),
        actor_ref="synthetic-user",
        request_id="synthetic-rule-request",
    )

    assert published.source_account_ref == "synthetic-account"

    overlapping = _rule(effective_from=datetime(2026, 2, 1, tzinfo=UTC))
    service.repository.lock_rule_versions.return_value = [overlapping]
    with pytest.raises(ApiError) as error:
        service.publish_rule(
            _pricing_rule_payload(version="synthetic-v2", effective_from=NOW),
            frozenset({"synthetic-account"}),
            actor_ref="synthetic-user",
            request_id="synthetic-overlap-request",
        )
    assert error.value.code == "RULE_VERSION_CONFLICT"

    service.repository.lock_rule_versions.return_value = []
    service.repository.add_rule.side_effect = IntegrityError(
        "synthetic concurrent open rule", {}, Exception()
    )
    with pytest.raises(ApiError) as concurrent:
        service.publish_rule(
            _pricing_rule_payload(version="synthetic-v3"),
            frozenset({"synthetic-account"}),
            actor_ref="synthetic-user",
            request_id="synthetic-concurrent-rule-request",
        )
    assert concurrent.value.code == "RULE_VERSION_CONFLICT"
    session.rollback.assert_called_once_with()


@pytest.mark.parametrize("existing", [False, True])
def test_pricing_rule_backdating_is_rejected_for_first_and_later_versions(
    monkeypatch: pytest.MonkeyPatch,
    existing: bool,
) -> None:
    monkeypatch.setattr("app.modules.product_management.service._utc_now", lambda: NOW)
    service = ProductManagementService(MagicMock(spec=Session))
    service.repository = MagicMock()
    service.repository.lock_rule_versions.return_value = (
        [_rule(effective_from=NOW - timedelta(days=2))] if existing else []
    )

    with pytest.raises(ApiError) as error:
        service.publish_rule(
            _pricing_rule_payload(
                version="synthetic-v2" if existing else "synthetic-v1",
                effective_from=NOW - timedelta(days=1),
            ),
            frozenset({"synthetic-account"}),
            actor_ref="synthetic-user",
            request_id="synthetic-backdating-request",
        )

    assert error.value.status_code == 422
    assert error.value.code == "PRICING_RULE_BACKDATING_NOT_ALLOWED"


@pytest.mark.parametrize(
    "changes",
    [
        {"effective_to": datetime(2026, 2, 1, tzinfo=UTC)},
        {"fx_date": "2026-01-01", "fx_source": None},
        {"grade_a_min_roi": "0.40", "grade_b_min_roi": "0.50"},
    ],
)
def test_pricing_rule_rejects_unsafe_interval_fx_or_grade_config(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        _pricing_rule_payload(**changes)
