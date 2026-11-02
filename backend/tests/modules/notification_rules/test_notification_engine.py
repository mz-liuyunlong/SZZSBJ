# ruff: noqa: E501
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.notification_rules.engine import (
    Condition,
    DeliveryPolicy,
    Expression,
    Group,
    RuleSpec,
    evaluate,
    ready_at,
    render_template,
    simulate,
)


def spec() -> RuleSpec:
    return RuleSpec(
        name="测试库存风险",
        event_key="inventory_alert",
        condition=Expression(
            logic="or",
            groups=[
                Group(
                    logic="and",
                    conditions=[
                        Condition(field="days_to_stockout", op="lte", value=7),
                        Condition(field="available_stock", op="lt", value=30),
                    ],
                ),
                Group(conditions=[Condition(field="risk_level", op="eq", value="critical")]),
            ],
        ),
    )


def test_and_or():
    expr = spec().condition
    assert evaluate(expr, {"days_to_stockout": 4, "available_stock": 12})[0] == "match"
    assert (
        evaluate(expr, {"days_to_stockout": 10, "available_stock": 99, "risk_level": "ok"})[0]
        == "no_match"
    )
    assert (
        evaluate(expr, {"days_to_stockout": 10, "available_stock": 99, "risk_level": "critical"})[0]
        == "match"
    )


def test_unknown_is_not_zero():
    assert evaluate(spec().condition, {"days_to_stockout": None})[0] == "unknown"


def test_invalid_field_rejected():
    with pytest.raises(ValidationError, match="UNREGISTERED_FIELD"):
        RuleSpec(
            name="不安全字段",
            event_key="inventory_alert",
            condition=Expression(
                groups=[Group(conditions=[Condition(field="query", op="eq", value="drop")])]
            ),
        )


def test_simulate_and_no_network():
    output = simulate(
        spec(),
        [
            {"object_key": "sku1", "facts": {"days_to_stockout": 3, "available_stock": 9}},
            {"object_key": "sku2", "facts": {}},
        ],
    )
    assert output["matches"] == 1 and output["unknowns"] == 1


def test_template_is_not_python_eval():
    assert (
        render_template(
            "{sku}: {message}", {"sku": "A"}, event_key="inventory_alert", message="异常"
        )
        == "A: 异常"
    )
    assert "__class__" in render_template("{message.__class__}", {}, event_key="x", message="x")


def test_quiet_hours():
    now = datetime(2026, 10, 31, 1, tzinfo=UTC)
    policy = DeliveryPolicy(quiet_from="00:00", quiet_until="10:00", timezone="UTC")
    ready = ready_at(policy, now)
    assert (ready.hour, ready.minute) == (10, 0)


def test_bad_scope():
    with pytest.raises(ValidationError, match="INVALID_SCOPE"):
        RuleSpec(
            name="坏范围",
            event_key="inventory_alert",
            scope={"bad": ["a"]},
            condition=Expression(
                groups=[Group(conditions=[Condition(field="available_stock", op="lt", value=1)])]
            ),
        )


def test_enabled_rule_requires_a_destination():
    data = spec().model_dump()
    data["enabled"] = True
    with pytest.raises(ValidationError, match="NOTIFICATION_RECIPIENT_REQUIRED"):
        RuleSpec.model_validate(data)
