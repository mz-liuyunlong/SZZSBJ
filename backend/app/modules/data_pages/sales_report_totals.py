"""Full-scope footer aggregates for the existing sales-report read models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, literal

ZERO = Decimal("0")
FX = Decimal("6.6")

# Keys are the existing export field identifiers (not arbitrary SQL identifiers).
MONEY_ATTRIBUTES = {
    "sales_amount": "sales_amount",
    "sample_amount": "sample_amount",
    "refund_amount": "refund_amount",
    "ad_spend": "ad_spend_amount",
    "sem_ad_spend": "sem_ad_spend_amount",
    "wfs_fee_total": "wfs_fee_total_amount",
    "wfs_low_price_surcharge": "wfs_low_price_surcharge_amount",
    "commission": "commission_fee_amount",
    "purchase_cost_total": "purchase_cost_total_usd",
    "first_leg_cost_total": "first_leg_cost_total_usd",
    "storage_fee_total": "storage_fee_total_amount",
    "order_profit": "gross_profit_amount",
}
COUNT_ATTRIBUTES = {
    "sales_qty": "sales_qty",
    "order_count": "order_count",
    "sample_qty": "sample_qty",
    "return_qty": "return_qty",
}

# These fields already use a zero default in the existing list DTO. Optional
# money/cost amounts remain unknown when any constituent amount is unavailable.
ZERO_DEFAULT = {
    "sales_qty",
    "order_count",
    "sales_amount",
    "sample_qty",
    "return_qty",
    "sem_ad_spend",
    "wfs_low_price_surcharge",
}


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    return result if result.is_finite() else None


def _add(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    return None if left is None or right is None else left + right


def _ratio(num: Decimal | None, den: Decimal | None, scale: int = 1) -> Decimal | None:
    if num is None or den is None or den <= ZERO:
        return None
    return num / den * scale


def _finish(
    usd: dict[str, Decimal | None],
    cny: dict[str, Decimal | None],
    inventory: Any,
    sample_evidence: str | None = None,
) -> dict[str, Any]:
    # Preserve the existing ratio definitions: ratios use source USD amounts,
    # while displayed unit amounts use totals in the selected display currency.
    for values in (usd, cny):
        values["wfs_inventory"] = _decimal(inventory)
        values["avg_price"] = _ratio(values["sales_amount"], values["sales_qty"])
        values["avg_profit_per_order"] = _ratio(values["order_profit"], values["order_count"])
        sales = values["sales_amount"]
        profit = values["order_profit"]
        values["total_cost"] = None if sales is None or profit is None else sales - profit
        # The rolling numerator/denominator are not persisted in this read model.
        # A selected-period return ratio is NOT a rolling 30-day return ratio.
        values["return_rate_30d"] = None
    ad_ratio = _ratio(usd["total_ad_spend"], usd["sales_amount"], 100)
    margin = _ratio(usd["order_profit"], usd["sales_amount"], 100)
    roi = _ratio(usd["order_profit"], _add(usd["purchase_cost_total"], usd["first_leg_cost_total"]))
    for values in (usd, cny):
        values.update(ad_ratio=ad_ratio, gross_margin=margin, roi=roi)
    return {"usd": usd, "cny": cny, "sample_evidence": sample_evidence}


def _strict_sum(expression: Any) -> Any:
    # Empty, known selection is zero; partial data is never presented as a
    # complete total. SQL COUNT(expression) ignores NULL, COUNT(*) does not.
    return case(
        (func.count(expression) == func.count(), func.coalesce(func.sum(expression), 0)),
        else_=None,
    )


def _sql_value(model: Any, key: str, attribute: str) -> Any:
    column = getattr(model, attribute, None)
    if column is None:
        return None
    return func.coalesce(column, 0) if key in ZERO_DEFAULT else column


def sql_aggregate_statement(statement: Any, model: Any, *, daily: bool) -> Any:
    """Aggregate in SQL before any paging or ordering; preserve exact WHERE scope."""
    fx = literal(FX)
    if daily:
        raw_fx = func.coalesce(model.exchange_rate, FX)
        fx = case((raw_fx > 0, raw_fx), else_=1)
    expressions = []
    for key, attribute in COUNT_ATTRIBUTES.items():
        value = _sql_value(model, key, attribute)
        total = literal(None) if value is None else _strict_sum(value)
        expressions.append(total.label("usd_" + key))
        expressions.append(total.label("cny_" + key))
    for key, attribute in MONEY_ATTRIBUTES.items():
        value = _sql_value(model, key, attribute)
        if value is None:
            usd_total = cny_total = literal(None)
        else:
            usd_total = _strict_sum(value)
            cny_value = value * fx
            if daily and key in ("sample_amount", "refund_amount"):
                # These two existing cells use the recorded row FX directly.
                cny_value = value * raw_fx
            if daily and key in ("purchase_cost_total", "first_leg_cost_total"):
                unit = (
                    model.purchase_cost_unit_cny
                    if key == "purchase_cost_total"
                    else model.first_leg_cost_unit_cny
                )
                quantity = func.coalesce(model.cost_quantity, 0)
                cny_value = case((unit.is_not(None), unit * quantity), else_=cny_value)
            cny_total = _strict_sum(cny_value)
        expressions.append(usd_total.label("usd_" + key))
        expressions.append(cny_total.label("cny_" + key))
    # Match the existing DTO definition of total advertising spend.
    ad = func.coalesce(model.ad_spend_amount, 0) + func.coalesce(model.sem_ad_spend_amount, 0)
    expressions.extend(
        (
            _strict_sum(ad).label("usd_total_ad_spend"),
            _strict_sum(ad * fx).label("cny_total_ad_spend"),
        )
    )
    warnings = getattr(model, "calculation_warnings_json", None) if daily else None
    for alias, code in (
        ("sample_pending", "sample_verification_pending"),
        ("sample_unknown", "sample_data_not_observed"),
    ):
        value = (
            func.count(case((warnings.has_key(code), 1), else_=None))
            if warnings is not None
            else literal(0)
        )
        expressions.append(value.label(alias))
    return (
        statement.order_by(None)
        .limit(None)
        .offset(None)
        .with_only_columns(
            *expressions,
            maintain_column_froms=True,
        )
    )


def merge_summary_statement(summary_statement: Any, model: Any, *, daily: bool) -> Any:
    """Append footer columns to the existing SELECT, without another scan."""
    footer = sql_aggregate_statement(summary_statement, model, daily=daily)
    return summary_statement.add_columns(*footer.selected_columns)


def sql_report_totals(
    session: Any,
    statement: Any,
    model: Any,
    *,
    daily: bool,
    inventory: Any = None,
) -> dict[str, Any]:
    row = session.execute(sql_aggregate_statement(statement, model, daily=daily)).mappings().one()
    return report_totals_from_mapping(row, inventory=inventory)


def report_totals_from_mapping(
    row: Mapping[str, Any],
    *,
    inventory: Any = None,
) -> dict[str, Any]:
    usd = {key: _decimal(row["usd_" + key]) for key in (*COUNT_ATTRIBUTES, *MONEY_ATTRIBUTES)}
    cny = {key: _decimal(row["cny_" + key]) for key in (*COUNT_ATTRIBUTES, *MONEY_ATTRIBUTES)}
    usd["total_ad_spend"] = _decimal(row["usd_total_ad_spend"])
    cny["total_ad_spend"] = _decimal(row["cny_total_ad_spend"])
    sample = "pending" if row["sample_pending"] else "unknown" if row["sample_unknown"] else None
    return _finish(usd, cny, inventory, sample)


def _complete_sum(rows: Sequence[Any], key: str, attribute: str) -> Decimal | None:
    total = ZERO
    for row in rows:
        if not hasattr(row, attribute):
            return None
        value = _decimal(getattr(row, attribute))
        if value is None:
            if key not in ZERO_DEFAULT:
                return None
            value = ZERO
        total += value
    return total


def range_report_totals(raw_rows: Sequence[Any], grouped_rows: Sequence[Any]) -> dict[str, Any]:
    """Existing range projection has already loaded and grouped its authorized rows.

    Costs/profit must be complete in the underlying item-day rows, not just the
    non-null subtotal of a group. Inventory is counted once per account + item.
    """
    eligible = [
        row
        for row in raw_rows
        if str(row.source_account_ref or "").strip() and str(row.item_id or "").strip()
    ]
    usd = {
        key: _complete_sum(eligible, key, attr)
        for key, attr in {**COUNT_ATTRIBUTES, **MONEY_ATTRIBUTES}.items()
    }
    cny = {
        key: (value * FX if key in MONEY_ATTRIBUTES and value is not None else value)
        for key, value in usd.items()
    }
    ad = sum(
        (
            (_decimal(row.ad_spend_amount) or ZERO) + (_decimal(row.sem_ad_spend_amount) or ZERO)
            for row in eligible
        ),
        ZERO,
    )
    usd["total_ad_spend"] = ad
    cny["total_ad_spend"] = ad * FX
    inventory = _complete_sum(grouped_rows, "wfs_inventory", "wfs_available_quantity")
    return _finish(usd, cny, inventory)


def redact_report_totals(
    totals: Any,
    *,
    gross_keys: set[str],
    margin_keys: set[str],
    can_view_gross_profit: bool,
    can_view_profit_margin: bool,
) -> Any:
    if totals is None:
        return None
    denied = set() if can_view_gross_profit else gross_keys.copy()
    if not (can_view_gross_profit and can_view_profit_margin):
        denied.update(margin_keys)

    def redact(values: Mapping[str, Any]) -> dict[str, Any]:
        return {key: None if key in denied else value for key, value in values.items()}

    return totals.model_copy(update={"usd": redact(totals.usd), "cny": redact(totals.cny)})
