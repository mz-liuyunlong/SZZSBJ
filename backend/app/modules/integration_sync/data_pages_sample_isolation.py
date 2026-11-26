"""Order-level verified sample isolation for governed Daily Sales capture.

The prior fact remains unchanged until provider evidence can be verified.
Anomaly review status is not authority to make disputed profit publishable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.integration_sync.models import (
    IntegrationSyncAnomaly,
    IntegrationSyncAnomalyAudit,
    utc_now,
)
from app.modules.integration_sync.repository import IntegrationSyncRepository

SAMPLE_CONFLICT_CODE = "DATA_PAGES_VERIFIED_SAMPLE_CHANGED"
SAMPLE_MISSING_CODE = "DATA_PAGES_VERIFIED_SAMPLE_NOT_OBSERVED"
SAMPLE_ALIAS_CODE = "DATA_PAGES_VERIFIED_LINE_ALIAS_AMBIGUOUS"
SAMPLE_CANCEL_CODE = "DATA_PAGES_SAMPLE_CANCELLATION_APPLIED"
SAMPLE_CONFLICT_WARNING = "sample_evidence_conflict_pending_review"
SAMPLE_CODES = (SAMPLE_CONFLICT_CODE, SAMPLE_MISSING_CODE, SAMPLE_ALIAS_CODE, SAMPLE_CANCEL_CODE)

VERIFIED_SAMPLE_EVIDENCE_FIELDS = (
    "business_date_utc_minus_7",
    "source_order_id",
    "platform_order_no",
    "store_id",
    "platform_code",
    "source_order_line_id",
    "item_id",
    "msku",
    "local_sku",
    "quantity",
    "unit_price_amount",
    "unit_price_currency_code",
    "order_total_amount",
    "order_total_currency_code",
    "cancel_time_raw",
    "is_cancelled",
)

# Only fixed internal aliases are interpolated; all source inputs are bound.
_SCOPE_MATCH = (
    "(scope->>'store_id' is null or scope->>'store_id'={row}.store_id) "
    "and ((scope->>'item_id' is null and scope->>'msku' is null) "
    "or scope->>'item_id'={row}.item_id or scope->>'msku'=trim({row}.msku))"
)
_SCOPE_ROWS = (
    "jsonb_array_elements(case when jsonb_typeof(a.details->'affected_products')='array' "
    "then a.details->'affected_products' else '[]'::jsonb end) scope"
)


def active_sample_scope_sql(row: str, day_column: str) -> str:
    if (row, day_column) not in {
        ("s", "business_date_utc_minus_7"),
        ("m", "business_date_la"),
    }:
        raise ValueError("unsupported sample isolation SQL scope")
    return (
        "exists (select 1 from gov_integration_sync_anomalies a "
        f"cross join lateral {_SCOPE_ROWS} "
        f"where a.source_account_ref={row}.source_account_ref "
        f"and a.business_date={row}.{day_column} "
        "and a.interface_key='saleStatPageList' "
        "and a.details->>'sample_isolation_active'='true' "
        f"and {_SCOPE_MATCH.format(row=row)})"
    )


def _identity(row: Mapping[str, object]) -> tuple[str, str]:
    return (str(row.get("platform_order_no") or ""), str(row.get("source_order_line_id") or ""))


def _subject(row: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(_identity(row), separators=(",", ":")).encode()).hexdigest()


def _safe_value(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    return str(value)[:500]


def _scope(row: Mapping[str, object]) -> dict[str, object]:
    return {key: _safe_value(row.get(key)) for key in ("store_id", "item_id", "msku")}


def _scopes(
    prior: Mapping[str, object], observed: Mapping[str, object] | None
) -> list[dict[str, object]]:
    result = [_scope(prior)]
    if observed is not None:
        other = _scope(observed)
        # A missing provider Item ID alone is not an identity change. Scope
        # the actual prior product and any positively identified observed one.
        if other["store_id"] is None:
            other["store_id"] = prior.get("store_id")
        if other["item_id"] is not None or other["msku"] is not None:
            if other not in result:
                result.append(other)
        elif other["store_id"] != result[0]["store_id"]:
            result.append(other)
    return result


def _evidence(
    prior: Mapping[str, object], observed: Mapping[str, object] | None
) -> list[dict[str, object]]:
    return [
        {
            "field": field,
            "previous": _safe_value(prior.get(field)),
            "observed": _safe_value(observed.get(field)) if observed is not None else None,
        }
        for field in VERIFIED_SAMPLE_EVIDENCE_FIELDS
        if observed is None or prior.get(field) != observed.get(field)
    ]


class SampleIsolation:
    """Only the governed sync enables this transaction-local evidence collector."""

    def __init__(self, session: Session, account: str, day: date, run_id: UUID) -> None:
        self.session = session
        self.account = account
        self.day = day
        self.run_id = run_id
        self.conflicted: set[str] = set()
        self.confirmed: set[str] = set()
        self.affected_days: set[date] = {day}
        self.raw: dict[tuple[str, str], dict[str, object]] = {}
        self.blocked_order_lines: set[tuple[str, str, str]] = set()

    def note_raw(self, row: dict[str, object], legacy_line_id: str | None) -> None:
        order, line = _identity(row)
        if order and line:
            self.raw[(order, line)] = row
            if legacy_line_id and legacy_line_id != line:
                self.raw.setdefault((order, legacy_line_id), row)

    def _record(
        self,
        prior: Mapping[str, object],
        observed: Mapping[str, object] | None,
        code: str,
        *,
        active: bool,
    ) -> None:
        subject = _subject(prior)
        dates = {self.day}
        if isinstance(prior.get("business_date_utc_minus_7"), date):
            prior_day = prior["business_date_utc_minus_7"]
            if isinstance(prior_day, date):
                dates.add(prior_day)
        self.affected_days.update(dates)
        details: dict[str, object] = {
            "phase": "sample_evidence",
            "financial_status": "pending",
            "sample_isolation_active": active,
            "affected_products": _scopes(prior, observed),
            "source_order_id": _safe_value(prior.get("source_order_id")),
            "source_order_line_id": _safe_value(prior.get("source_order_line_id")),
            "store_name": _safe_value(prior.get("store_name")),
            "changes": _evidence(prior, observed),
            "reason": code,
            "provider_observed": observed is not None,
        }
        repo = IntegrationSyncRepository(self.session)
        for day in sorted(dates):
            repo.record_business_anomaly(
                run_id=self.run_id,
                account=self.account,
                interface_key="saleStatPageList",
                business_date=day,
                error_code=code,
                subject_key=subject,
                store_id=_text(prior.get("store_id")),
                item_id=_text(prior.get("item_id")),
                msku=_text(prior.get("msku")),
                local_sku=_text(prior.get("local_sku")),
                platform_order_no=_text(prior.get("platform_order_no")),
                details=details,
            )

    def conflict(
        self,
        prior: Mapping[str, object],
        observed: Mapping[str, object] | None,
        code: str = SAMPLE_CONFLICT_CODE,
    ) -> None:
        self.conflicted.add(_subject(prior))
        raw = self.raw.get(_identity(prior))
        if observed is None:
            observed = raw
        if raw is not None:
            observed_order, observed_line = _identity(raw)
            store = str(raw.get("store_id") or "")
            source = str(raw.get("source_order_id") or "")
            if observed_order and observed_line and store and source:
                self.blocked_order_lines.add((store, source, observed_line))
        elif observed is not None:
            observed_line = str(observed.get("source_order_line_id") or "")
            store = str(observed.get("store_id") or "")
            source = str(observed.get("source_order_id") or "")
            if observed_line and store and source:
                self.blocked_order_lines.add((store, source, observed_line))
        self._record(prior, observed, code, active=True)

    def missing(self, prior: Mapping[str, object]) -> None:
        if _subject(prior) not in self.conflicted:
            self.conflict(prior, self.raw.get(_identity(prior)), SAMPLE_MISSING_CODE)

    def observe(
        self,
        prior: Mapping[str, object],
        observed: Mapping[str, object],
        *,
        cancellation_changed: bool = False,
    ) -> None:
        self.confirmed.add(_subject(prior))
        if cancellation_changed:
            self._record(prior, observed, SAMPLE_CANCEL_CODE, active=False)

    def finish(self) -> None:
        # A duplicate conflicting observation in the same source batch wins
        # over an identical replay; don't clear uncertainty by arrival order.
        resolved = self.confirmed - self.conflicted
        if not resolved:
            return
        rows = self.session.scalars(
            select(IntegrationSyncAnomaly)
            .where(
                IntegrationSyncAnomaly.source_account_ref == self.account,
                IntegrationSyncAnomaly.interface_key == "saleStatPageList",
                IntegrationSyncAnomaly.business_date == self.day,
                IntegrationSyncAnomaly.subject_key.in_(resolved),
                IntegrationSyncAnomaly.details["sample_isolation_active"].astext == "true",
            )
            .with_for_update()
        ).all()
        for row in rows:
            row.details = {
                **row.details,
                "sample_isolation_active": False,
                "financial_status": "pending",
                "provider_replay_verified": True,
            }
            row.run_id = self.run_id
            row.last_seen_at = utc_now()
            _status(self.session, row, "review_pending", "来源证据已恢复，等待销售利润复验。")

    def filter_order_facts(self, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.blocked_order_lines:
            return orders
        filtered = []
        for row in orders:
            items = row.get("item_info")
            if not isinstance(items, list):
                filtered.append(row)
                continue
            store = _provider_field(row, "store_id")
            source = _provider_field(row, "global_order_no", "order_id", "platform_order_no")
            remaining = [
                item
                for item in items
                if not isinstance(item, dict)
                or (
                    store,
                    source,
                    _provider_field(item, "order_item_no", "global_item_no", "id"),
                )
                not in self.blocked_order_lines
            ]
            if remaining:
                filtered.append({**row, "item_info": remaining})
        return filtered


def _provider_field(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            if normalized := str(value).strip():
                return normalized
    return ""


def _text(value: object) -> str | None:
    return str(value) if value is not None else None


def _status(session: Session, row: IntegrationSyncAnomaly, status: str, note: str) -> None:
    if row.status == status:
        return
    session.add(
        IntegrationSyncAnomalyAudit(
            anomaly_id=row.id,
            actor_ref="system",
            from_status=row.status,
            to_status=status,
            note=note,
        )
    )
    row.status = status
    row.updated_by = "system"
    row.resolved_at = utc_now() if status == "resolved" else None


def complete_sample_financial_review(
    session: Session, account: str, day: date, run_id: UUID
) -> None:
    """Call only after both financial MARTs passed their replay validation."""
    rows = session.scalars(
        select(IntegrationSyncAnomaly)
        .where(
            IntegrationSyncAnomaly.source_account_ref == account,
            IntegrationSyncAnomaly.interface_key == "saleStatPageList",
            IntegrationSyncAnomaly.business_date == day,
            IntegrationSyncAnomaly.error_code.in_(SAMPLE_CODES),
        )
        .with_for_update()
    ).all()
    has_active = any(row.details.get("sample_isolation_active") is True for row in rows)
    for row in rows:
        marker = row.details.get("sample_isolation_active")
        if marker is True or marker is False:
            if row.details.get("financial_status") == "pending":
                row.details = {
                    **row.details,
                    "financial_status": "partial" if marker else "ready",
                }
                if not marker:
                    _status(session, row, "resolved", "来源和销售利润复验完成。")
        elif (
            row.subject_key == "date-scope"
            and not has_active
            and row.status
            not in {
                "resolved",
                "dismissed",
            }
        ):
            row.details = {**row.details, "financial_status": "ready", "validated_run": str(run_id)}
            _status(session, row, "resolved", "整日来源和销售利润已重新同步并复验。")


def mark_isolated_sample_finance(session: Session, account: str, day: date) -> None:
    # Keep gross provider sales visible as provisional, never deduct an
    # unverified sample or publish a fabricated paid-sale profit.
    predicate = active_sample_scope_sql("m", "business_date_la")
    session.execute(
        text(
            "update mart_daily_sales_item_day m set cost_quantity=gross_sales_qty,"
            "sales_qty=gross_sales_qty,order_count=gross_order_count,"
            "sales_amount=gross_sales_amount,sales_amount_excluding_sample=gross_sales_amount,"
            "refund_amount=null,commission_fee_amount=null,ad_ratio=null,"
            "calculation_warnings_json=jsonb_build_array(cast(:warning as text)) "
            "where m.source_account_ref=:account and m.business_date_la=:day "
            f"and {predicate}"
        ),
        {"account": account, "day": day, "warning": SAMPLE_CONFLICT_WARNING},
    )

