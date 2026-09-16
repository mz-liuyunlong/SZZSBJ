from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from app.modules.integration_sync.data_pages_catalog import (
    DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY,
)
from app.modules.integration_sync.data_pages_mart_refresh import (
    build_mart_refresh_plan,
    mart_refresh_keys,
)
from app.modules.integration_sync.data_pages_request_plans import (
    DATA_PAGES_REQUEST_PLAN_SPECS_BY_KEY,
)
from app.modules.integration_sync.data_pages_writer_specs import (
    DATA_PAGES_WRITER_SPECS_BY_KEY,
    SOURCE_METADATA_FIELDS,
)
from app.modules.integration_sync.parsers.lingxing_data_pages import (
    DATA_PAGES_PARSER_SPECS,
    DataPagesParserKey,
)

FixtureSeverity = Literal["error", "warning"]

_SENSITIVE_KEY_MARKERS: Final = (
    "token",
    "secret",
    "authorization",
    "password",
    "sign",
    "payload",
    "raw",
)


@dataclass(frozen=True, slots=True)
class DataPagesFixtureCase:
    """Synthetic fixture contract for one DATA-PAGES source interface.

    A fixture case records only display-safe metadata and expected normalized fields.
    It must never contain real payloads, credentials, SKU values, or order identifiers.
    """

    parser_key: DataPagesParserKey
    fixture_name: str
    available_target_fields: tuple[str, ...]
    request_metadata: Mapping[str, object]
    observed_record_count: int
    observed_return_types: tuple[str, ...] = ()
    boundary_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DataPagesFixtureValidationIssue:
    parser_key: DataPagesParserKey
    fixture_name: str
    code: str
    detail: str
    severity: FixtureSeverity = "error"


@dataclass(frozen=True, slots=True)
class DataPagesFixtureValidationReport:
    validated_interfaces: int
    fixture_cases: int
    required_field_checks: int
    unique_key_checks: int
    request_rule_checks: int
    mart_plan_checks: int
    sensitive_field_checks: int
    production_calls: bool
    production_writes: bool
    issues: tuple[DataPagesFixtureValidationIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues and not self.production_calls and not self.production_writes



def _request_metadata_for(parser_key: DataPagesParserKey) -> dict[str, object]:
    plan = DATA_PAGES_REQUEST_PLAN_SPECS_BY_KEY[parser_key]
    metadata: dict[str, object] = dict(plan.static_body_fields)
    if plan.fanout_field is not None:
        metadata[plan.fanout_field] = plan.fanout_values
    if plan.dependency_parser_key is not None:
        metadata["depends_on"] = plan.dependency_parser_key
    if plan.date_window_kind != "none":
        metadata["date_window_kind"] = plan.date_window_kind
    if plan.store_scope_field is not None:
        metadata["store_scope_field"] = plan.store_scope_field
    return metadata



def _available_target_fields_for(parser_key: DataPagesParserKey) -> tuple[str, ...]:
    parser_spec = DATA_PAGES_PARSER_SPECS[parser_key]
    writer_spec = DATA_PAGES_WRITER_SPECS_BY_KEY[parser_key]
    fields = (
        *(field.target_name for field in parser_spec.fields if field.required),
        *writer_spec.unique_key,
        *SOURCE_METADATA_FIELDS,
    )
    return tuple(dict.fromkeys(fields))


DATA_PAGES_FIXTURE_CASES: Final[tuple[DataPagesFixtureCase, ...]] = tuple(
    DataPagesFixtureCase(
        parser_key=parser_key,
        fixture_name=f"synthetic-{parser_key.replace('_', '-')}",
        available_target_fields=_available_target_fields_for(parser_key),
        request_metadata=_request_metadata_for(parser_key),
        observed_record_count=1,
        observed_return_types=("REFUND",) if parser_key == "walmart_return_order_list" else (),
        boundary_notes=(
            "Synthetic fixture only; no real Lingxing payload or production data.",
        ),
    )
    for parser_key in DATA_PAGES_PARSER_SPECS
)

DATA_PAGES_FIXTURE_CASES_BY_KEY: Final = {
    fixture.parser_key: fixture for fixture in DATA_PAGES_FIXTURE_CASES
}



def data_pages_fixture_parser_keys() -> frozenset[DataPagesParserKey]:
    return frozenset(DATA_PAGES_FIXTURE_CASES_BY_KEY)



def validate_data_pages_fixture_contracts(
    fixtures: tuple[DataPagesFixtureCase, ...] = DATA_PAGES_FIXTURE_CASES,
) -> DataPagesFixtureValidationReport:
    issues: list[DataPagesFixtureValidationIssue] = []
    required_field_checks = 0
    unique_key_checks = 0
    request_rule_checks = 0
    sensitive_field_checks = 0

    fixture_keys = frozenset(fixture.parser_key for fixture in fixtures)
    expected_keys = frozenset(DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY)
    if fixture_keys != expected_keys:
        missing = sorted(expected_keys - fixture_keys)
        extra = sorted(fixture_keys - expected_keys)
        issues.append(
            DataPagesFixtureValidationIssue(
                parser_key="seller_list_multi_platform",
                fixture_name="fixture-set",
                code="DATA_PAGES_FIXTURE_COVERAGE_MISMATCH",
                detail=f"missing={missing}; extra={extra}",
            )
        )

    for fixture in fixtures:
        if fixture.observed_record_count < 1:
            issues.append(
                _issue(
                    fixture,
                    "DATA_PAGES_FIXTURE_EMPTY",
                    "fixture must include at least one synthetic normalized record",
                )
            )
        if _contains_sensitive_key(fixture.request_metadata):
            issues.append(
                _issue(
                    fixture,
                    "DATA_PAGES_FIXTURE_UNSAFE_REQUEST_METADATA",
                    "request metadata cannot contain credential, raw, or payload keys",
                )
            )
        sensitive_field_checks += 1
        required_field_checks += _validate_required_fields(fixture, issues)
        unique_key_checks += _validate_unique_key_fields(fixture, issues)
        request_rule_checks += _validate_request_rules(fixture, issues)

    mart_plan_checks = _validate_mart_plans(issues)

    return DataPagesFixtureValidationReport(
        validated_interfaces=len(fixture_keys),
        fixture_cases=len(fixtures),
        required_field_checks=required_field_checks,
        unique_key_checks=unique_key_checks,
        request_rule_checks=request_rule_checks,
        mart_plan_checks=mart_plan_checks,
        sensitive_field_checks=sensitive_field_checks,
        production_calls=False,
        production_writes=False,
        issues=tuple(issues),
    )



def _validate_required_fields(
    fixture: DataPagesFixtureCase,
    issues: list[DataPagesFixtureValidationIssue],
) -> int:
    parser_spec = DATA_PAGES_PARSER_SPECS[fixture.parser_key]
    required_fields = tuple(field.target_name for field in parser_spec.fields if field.required)
    missing = tuple(field for field in required_fields if field not in fixture.available_target_fields)
    if missing:
        issues.append(
            _issue(
                fixture,
                "DATA_PAGES_FIXTURE_REQUIRED_FIELDS_MISSING",
                f"missing required normalized fields: {missing}",
            )
        )
    return len(required_fields)



def _validate_unique_key_fields(
    fixture: DataPagesFixtureCase,
    issues: list[DataPagesFixtureValidationIssue],
) -> int:
    writer_spec = DATA_PAGES_WRITER_SPECS_BY_KEY[fixture.parser_key]
    missing = tuple(
        field for field in writer_spec.unique_key if field not in fixture.available_target_fields
    )
    if missing:
        issues.append(
            _issue(
                fixture,
                "DATA_PAGES_FIXTURE_UNIQUE_KEY_FIELDS_MISSING",
                f"missing writer unique-key fields: {missing}",
            )
        )
    return len(writer_spec.unique_key)



def _validate_request_rules(
    fixture: DataPagesFixtureCase,
    issues: list[DataPagesFixtureValidationIssue],
) -> int:
    plan = DATA_PAGES_REQUEST_PLAN_SPECS_BY_KEY[fixture.parser_key]
    check_count = 1
    for field, expected_value in plan.static_body_fields:
        if fixture.request_metadata.get(field) != expected_value:
            issues.append(
                _issue(
                    fixture,
                    "DATA_PAGES_FIXTURE_STATIC_REQUEST_FIELD_MISMATCH",
                    f"{field} must equal {expected_value!r}",
                )
            )
    if plan.fanout_field is not None:
        check_count += 1
        if fixture.request_metadata.get(plan.fanout_field) != plan.fanout_values:
            issues.append(
                _issue(
                    fixture,
                    "DATA_PAGES_FIXTURE_FANOUT_MISMATCH",
                    f"{plan.fanout_field} must equal {plan.fanout_values!r}",
                )
            )
    if plan.dependency_parser_key is not None:
        check_count += 1
        if fixture.request_metadata.get("depends_on") != plan.dependency_parser_key:
            issues.append(
                _issue(
                    fixture,
                    "DATA_PAGES_FIXTURE_DEPENDENCY_MISSING",
                    f"depends_on must equal {plan.dependency_parser_key}",
                )
            )
    if fixture.parser_key == "walmart_return_order_list":
        check_count += 1
        if set(fixture.observed_return_types) != {"REFUND"}:
            issues.append(
                _issue(
                    fixture,
                    "DATA_PAGES_FIXTURE_RETURN_TYPE_NOT_REFUND_ONLY",
                    "return fixtures must contain REFUND records only",
                )
            )
    return check_count



def _validate_mart_plans(issues: list[DataPagesFixtureValidationIssue]) -> int:
    check_count = 0
    for key in sorted(mart_refresh_keys()):
        if key == "listing_management":
            build_mart_refresh_plan(key, source_account_ref="fixture-account")
        else:
            build_mart_refresh_plan(
                key,
                source_account_ref="fixture-account",
                business_date_from=date(2026, 9, 1),
                business_date_to=date(2026, 9, 1),
            )
        check_count += 1
    if check_count != 3:
        issues.append(
            DataPagesFixtureValidationIssue(
                parser_key="seller_list_multi_platform",
                fixture_name="mart-refresh-plan-set",
                code="DATA_PAGES_FIXTURE_MART_PLAN_COVERAGE_MISMATCH",
                detail="expected exactly three DATA-PAGES MART refresh plans",
            )
        )
    return check_count



def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            key_text = str(key).lower()
            if any(marker in key_text for marker in _SENSITIVE_KEY_MARKERS):
                return True
            if _contains_sensitive_key(nested_value):
                return True
    elif isinstance(value, tuple | list):
        return any(_contains_sensitive_key(item) for item in value)
    return False



def _issue(
    fixture: DataPagesFixtureCase,
    code: str,
    detail: str,
) -> DataPagesFixtureValidationIssue:
    return DataPagesFixtureValidationIssue(
        parser_key=fixture.parser_key,
        fixture_name=fixture.fixture_name,
        code=code,
        detail=detail,
    )
