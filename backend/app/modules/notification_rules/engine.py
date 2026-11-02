# ruff: noqa: E501
"""Pure and safe notification rule evaluator. No SQL, eval, or external I/O."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# Explicit field registration: unknown fields are rejected rather than used as SQL paths.
FIELDS: dict[str, dict[str, str]] = {
    "inventory_alert": {
        "platform": "text",
        "store": "text",
        "warehouse": "text",
        "sku": "text",
        "owner": "text",
        "available_stock": "number",
        "inbound_stock": "number",
        "days_to_stockout": "number",
        "daily_sales_7d": "number",
        "risk_level": "enum",
    },
    "sync_failed": {
        "platform": "text",
        "store": "text",
        "job_type": "text",
        "failed_minutes": "number",
        "retry_count": "number",
        "risk_level": "enum",
    },
    "ads_alert": {
        "platform": "text",
        "store": "text",
        "sku": "text",
        "owner": "text",
        "spend_7d": "number",
        "acos_7d": "number",
        "roas_7d": "number",
        "clicks_7d": "number",
        "orders_7d": "number",
        "zero_order_days": "number",
        "risk_level": "enum",
    },
    "approval_pending": {
        "platform": "text",
        "store": "text",
        "approval_type": "text",
        "wait_hours": "number",
        "amount": "number",
        "risk_level": "enum",
    },
    "ai_completed": {
        "task_type": "text",
        "duration_seconds": "number",
        "risk_level": "enum",
    },
    "finance_completed": {
        "platform": "text",
        "store": "text",
        "sku": "text",
        "profit": "number",
        "margin_percent": "number",
        "refund_amount": "number",
        "risk_level": "enum",
    },
    "purchase_alert": {
        "platform": "text",
        "store": "text",
        "sku": "text",
        "supplier": "text",
        "overdue_days": "number",
        "purchase_qty": "number",
        "risk_level": "enum",
    },
    "shipping_alert": {
        "platform": "text",
        "store": "text",
        "sku": "text",
        "carrier": "text",
        "unshipped_hours": "number",
        "no_tracking_days": "number",
        "risk_level": "enum",
    },
    "listing_alert": {
        "platform": "text",
        "store": "text",
        "sku": "text",
        "rating": "number",
        "review_count": "number",
        "has_buybox": "bool",
        "risk_level": "enum",
    },
    "sales_alert": {
        "platform": "text",
        "store": "text",
        "sku": "text",
        "sales_7d": "number",
        "sales_change_pct": "number",
        "profit_7d": "number",
        "margin_7d": "number",
        "risk_level": "enum",
    },
}
NUMERIC_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "between"}
TEXT_OPS = {"eq", "ne", "contains", "in", "not_in"}
TRI = Literal["match", "no_match", "unknown"]


class Condition(BaseModel):
    field: str = Field(min_length=1, max_length=80)
    op: str = Field(min_length=1, max_length=24)
    value: Any


class Group(BaseModel):
    logic: Literal["and", "or"] = "and"
    conditions: list[Condition] = Field(default_factory=list, min_length=1, max_length=20)


class Expression(BaseModel):
    logic: Literal["and", "or"] = "and"
    groups: list[Group] = Field(default_factory=list, min_length=1, max_length=10)


class RecipientSet(BaseModel):
    group_ids: list[str] = Field(default_factory=list, max_length=30)
    people_ids: list[str] = Field(default_factory=list, max_length=50)
    dynamic_roles: list[
        Literal["sku_owner", "store_owner", "buyer", "approver", "warehouse_owner", "supervisor"]
    ] = Field(default_factory=list, max_length=6)
    group_mention: bool = False


class Branch(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    when: Expression
    recipients: RecipientSet
    group_template: str = Field(default="【{event_key}】\n{message}", max_length=2000)
    personal_template: str = Field(default="【{event_key}】\n{message}", max_length=2000)


class DeliveryPolicy(BaseModel):
    mode: Literal["immediate", "daily", "aggregate"] = "immediate"
    daily_time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: Literal["Asia/Shanghai", "America/New_York", "UTC"] = "Asia/Shanghai"
    aggregate_minutes: int = Field(default=30, ge=5, le=1440)
    quiet_from: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_until: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    cooldown_minutes: int = Field(default=60, ge=0, le=10080)
    daily_limit: int = Field(default=100, ge=1, le=10000)
    trigger: Literal["on_enter", "repeat"] = "on_enter"
    send_recovery: bool = True
    debounce_samples: int = Field(default=1, ge=1, le=10)
    escalation_minutes: int = Field(default=0, ge=0, le=10080)
    escalation_recipients: RecipientSet = Field(default_factory=RecipientSet)

    @model_validator(mode="after")
    def validate_quiet(self) -> DeliveryPolicy:
        if bool(self.quiet_from) != bool(self.quiet_until):
            raise ValueError("quiet_from and quiet_until must both be set")
        return self


class RuleSpec(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    event_key: str
    enabled: bool = False
    scope: dict[str, list[str]] = Field(default_factory=dict)
    condition: Expression
    recovery_condition: Expression | None = None
    branches: list[Branch] = Field(default_factory=list, max_length=8)
    recipients: RecipientSet = Field(default_factory=RecipientSet)
    group_template: str = Field(default="【{event_key}】\n{message}", max_length=2000)
    personal_template: str = Field(default="【{event_key}】\n{message}", max_length=2000)
    policy: DeliveryPolicy = Field(default_factory=DeliveryPolicy)

    @model_validator(mode="after")
    def validate_fields(self) -> RuleSpec:
        declared = FIELDS.get(self.event_key)
        if declared is None:
            raise ValueError("UNSUPPORTED_EVENT_KEY")

        def validate(expression: Expression) -> None:
            for group in expression.groups:
                for c in group.conditions:
                    kind = declared.get(c.field)
                    if not kind:
                        raise ValueError(f"UNREGISTERED_FIELD:{c.field}")
                    if c.op not in (
                        NUMERIC_OPS
                        if kind == "number"
                        else TEXT_OPS
                        if kind in ("enum", "text")
                        else {"eq", "ne"}
                    ):
                        raise ValueError(f"INVALID_OPERATOR:{c.field}")
                    if kind == "number":
                        values = c.value if c.op == "between" else [c.value]
                        if not isinstance(values, list) or (c.op == "between" and len(values) != 2):
                            raise ValueError("INVALID_NUMERIC_VALUE")
                        try:
                            for value in values:
                                if not Decimal(str(value)).is_finite():
                                    raise ValueError("NONFINITE_VALUE")
                        except InvalidOperation:
                            raise ValueError("INVALID_NUMERIC_VALUE") from None
                    if c.op in ("in", "not_in") and not isinstance(c.value, list):
                        raise ValueError("INVALID_LIST_VALUE")

        validate(self.condition)
        if self.recovery_condition is not None:
            validate(self.recovery_condition)
        if self.enabled:
            targets = [self.recipients, *(b.recipients for b in self.branches)]
            if not any(t.group_ids or t.people_ids or t.dynamic_roles for t in targets):
                raise ValueError("NOTIFICATION_RECIPIENT_REQUIRED")
        for branch in self.branches:
            validate(branch.when)
        for key, values in self.scope.items():
            if key not in declared or declared[key] not in ("text", "enum") or len(values) > 100:
                raise ValueError("INVALID_SCOPE")
        return self


def _one(c: Condition, facts: dict[str, Any]) -> TRI:
    if c.field not in facts or facts[c.field] is None or facts[c.field] == "":
        return "unknown"
    actual = facts[c.field]
    try:
        field_kind = next((types[c.field] for types in FIELDS.values() if c.field in types), None)
        if field_kind == "number":
            left = Decimal(str(actual))
            if not left.is_finite():
                return "unknown"
            if c.op == "between":
                lo, hi = (Decimal(str(v)) for v in c.value)
                return "match" if lo <= left <= hi else "no_match"
            right = Decimal(str(c.value))
            result = {
                "eq": left == right,
                "ne": left != right,
                "gt": left > right,
                "gte": left >= right,
                "lt": left < right,
                "lte": left <= right,
            }[c.op]
        elif isinstance(actual, bool):
            if not isinstance(c.value, bool):
                return "unknown"
            result = actual == c.value if c.op == "eq" else actual != c.value
        else:
            left = str(actual)
            if c.op == "contains":
                result = str(c.value).casefold() in left.casefold()
            elif c.op == "in":
                result = left in [str(v) for v in c.value]
            elif c.op == "not_in":
                result = left not in [str(v) for v in c.value]
            elif c.op == "eq":
                result = left == str(c.value)
            else:
                result = left != str(c.value)
        return "match" if result else "no_match"
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return "unknown"


def _combine(results: list[TRI], logic: str) -> TRI:
    if logic == "and":
        if "no_match" in results:
            return "no_match"
        if "unknown" in results:
            return "unknown"
        return "match"
    if "match" in results:
        return "match"
    if "unknown" in results:
        return "unknown"
    return "no_match"


def evaluate(expr: Expression, facts: dict[str, Any]) -> tuple[TRI, list[dict[str, Any]]]:
    traces = []
    results: list[TRI] = []
    for group in expr.groups:
        checks = [
            {
                "field": c.field,
                "op": c.op,
                "expected": c.value,
                "actual": facts.get(c.field),
                "result": _one(c, facts),
            }
            for c in group.conditions
        ]
        status = _combine([c["result"] for c in checks], group.logic)
        traces.append({"logic": group.logic, "result": status, "conditions": checks})
        results.append(status)
    return _combine(results, expr.logic), traces


def simulate(rule: RuleSpec, samples: list[dict[str, Any]]) -> dict[str, Any]:
    matches = unknowns = 0
    results = []
    for sample in samples[:300]:
        facts = sample.get("facts", {})
        if not isinstance(facts, dict):
            facts = {}
        scope_missing = any(
            v and (k not in facts or facts[k] is None) for k, v in rule.scope.items()
        )
        scope_ok = all(not v or str(facts.get(k)) in v for k, v in rule.scope.items())
        status, trace = (
            ("unknown", [])
            if scope_missing
            else evaluate(rule.condition, facts)
            if scope_ok
            else ("no_match", [])
        )
        if status == "match":
            matches += 1
        if status == "unknown":
            unknowns += 1
        branches = [
            b.label
            for b in rule.branches
            if status == "match" and evaluate(b.when, facts)[0] == "match"
        ]
        results.append(
            {
                "object_key": str(sample.get("object_key", "")),
                "result": status,
                "trace": trace,
                "branches": branches,
            }
        )
    return {
        "total": len(results),
        "matches": matches,
        "unknowns": unknowns,
        "no_matches": len(results) - matches - unknowns,
        "results": results,
    }


def render_template(template: str, facts: dict[str, Any], *, event_key: str, message: str) -> str:
    """Only simple registered fields are interpolated, never Python formatting syntax."""
    import re

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        value = (
            event_key
            if key == "event_key"
            else message
            if key == "message"
            else facts.get(key, "—")
            if key in FIELDS.get(event_key, {})
            else "—"
        )
        return str(value)[:250]

    return re.sub(r"\{([a-z][a-z0-9_]*)\}", substitute, template)[:2000]


def ready_at(policy: DeliveryPolicy, now: datetime) -> datetime:
    """Quiet-hours and batching resolution, timezone-aware, deterministic."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    local = now.astimezone(ZoneInfo(policy.timezone))
    if policy.mode == "aggregate":
        local += timedelta(minutes=policy.aggregate_minutes)
    elif policy.mode == "daily":
        hh, mm = (int(x) for x in policy.daily_time.split(":"))
        target = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        local = target if target > local else target + timedelta(days=1)
    if policy.quiet_from and policy.quiet_until:
        start = policy.quiet_from
        end = policy.quiet_until
        minute = local.hour * 60 + local.minute
        a, b = [int(t[:2]) * 60 + int(t[3:]) for t in (start, end)]
        inside = (a <= minute < b) if a < b else (minute >= a or minute < b)
        if inside:
            hh, mm = divmod(b, 60)
            local = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if (a >= b) and minute >= a:
                local += timedelta(days=1)
    return local.astimezone(now.tzinfo)
