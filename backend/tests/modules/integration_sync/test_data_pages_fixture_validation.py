from dataclasses import replace

from app.modules.integration_sync.data_pages_catalog import data_pages_sync_parser_keys
from app.modules.integration_sync.data_pages_fixture_validation import (
    DATA_PAGES_FIXTURE_CASES,
    DATA_PAGES_FIXTURE_CASES_BY_KEY,
    data_pages_fixture_parser_keys,
    validate_data_pages_fixture_contracts,
)
from app.modules.integration_sync.data_pages_mart_refresh import mart_refresh_keys
from app.modules.integration_sync.data_pages_request_plans import (
    DATA_PAGES_REQUEST_PLAN_SPECS_BY_KEY,
)
from app.modules.integration_sync.data_pages_writer_specs import DATA_PAGES_WRITER_SPECS_BY_KEY
from app.modules.integration_sync.parsers.lingxing_data_pages import DATA_PAGES_PARSER_SPECS


def test_fixture_cases_cover_every_data_pages_source_interface() -> None:
    assert data_pages_fixture_parser_keys() == data_pages_sync_parser_keys()
    assert len(DATA_PAGES_FIXTURE_CASES) == 7

    for parser_key, fixture in DATA_PAGES_FIXTURE_CASES_BY_KEY.items():
        assert fixture.parser_key == parser_key
        assert fixture.observed_record_count == 1
        assert "source_raw_request_ref_id" in fixture.available_target_fields
        assert "Synthetic fixture only" in fixture.boundary_notes[0]


def test_fixture_validation_report_passes_without_production_effects() -> None:
    report = validate_data_pages_fixture_contracts()

    expected_required_checks = sum(
        1 for spec in DATA_PAGES_PARSER_SPECS.values() for field in spec.fields if field.required
    )
    expected_unique_key_checks = sum(
        len(spec.unique_key) for spec in DATA_PAGES_WRITER_SPECS_BY_KEY.values()
    )

    assert report.passed is True
    assert report.validated_interfaces == 7
    assert report.fixture_cases == 7
    assert report.required_field_checks == expected_required_checks
    assert report.unique_key_checks == expected_unique_key_checks
    assert report.request_rule_checks >= 7
    assert report.mart_plan_checks == len(mart_refresh_keys())
    assert report.sensitive_field_checks == 7
    assert report.production_calls is False
    assert report.production_writes is False
    assert report.issues == ()


def test_fixture_validation_rejects_sensitive_request_metadata() -> None:
    fixture = DATA_PAGES_FIXTURE_CASES_BY_KEY["seller_list_multi_platform"]
    unsafe_fixture = replace(
        fixture,
        request_metadata={**fixture.request_metadata, "access_token": "redacted"},
    )

    report = validate_data_pages_fixture_contracts((unsafe_fixture,))

    assert report.passed is False
    assert any(
        issue.code == "DATA_PAGES_FIXTURE_UNSAFE_REQUEST_METADATA" for issue in report.issues
    )


def test_fixture_validation_rejects_missing_required_fields() -> None:
    fixture = DATA_PAGES_FIXTURE_CASES_BY_KEY["walmart_listing_list"]
    incomplete_fixture = replace(
        fixture,
        available_target_fields=tuple(
            field for field in fixture.available_target_fields if field != "store_id"
        ),
    )

    report = validate_data_pages_fixture_contracts((incomplete_fixture,))

    assert report.passed is False
    assert any(
        issue.code == "DATA_PAGES_FIXTURE_REQUIRED_FIELDS_MISSING" for issue in report.issues
    )
    assert any(
        issue.code == "DATA_PAGES_FIXTURE_UNIQUE_KEY_FIELDS_MISSING" for issue in report.issues
    )


def test_fixture_validation_enforces_request_planning_rules() -> None:
    sale_stat = DATA_PAGES_FIXTURE_CASES_BY_KEY["sale_stat_page_list"]
    broken_sale_stat = replace(
        sale_stat,
        request_metadata={**sale_stat.request_metadata, "result_type": (1,)},
    )

    report = validate_data_pages_fixture_contracts((broken_sale_stat,))

    assert report.passed is False
    assert any(issue.code == "DATA_PAGES_FIXTURE_FANOUT_MISMATCH" for issue in report.issues)


def test_fixture_validation_keeps_return_fixtures_refund_only() -> None:
    fixture = DATA_PAGES_FIXTURE_CASES_BY_KEY["walmart_return_order_list"]
    non_refund_fixture = replace(fixture, observed_return_types=("REFUND", "RETURN"))

    report = validate_data_pages_fixture_contracts((non_refund_fixture,))

    assert report.passed is False
    assert any(
        issue.code == "DATA_PAGES_FIXTURE_RETURN_TYPE_NOT_REFUND_ONLY" for issue in report.issues
    )


def test_fixture_cases_capture_request_plan_static_fields() -> None:
    for parser_key, plan in DATA_PAGES_REQUEST_PLAN_SPECS_BY_KEY.items():
        fixture = DATA_PAGES_FIXTURE_CASES_BY_KEY[parser_key]
        for field, expected_value in plan.static_body_fields:
            assert fixture.request_metadata[field] == expected_value
        if plan.dependency_parser_key is not None:
            assert fixture.request_metadata["depends_on"] == plan.dependency_parser_key
