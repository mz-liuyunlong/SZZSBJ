"""Schema-free notification management guards; no database/network use."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.notification_rules.engine import RuleSpec
from app.modules.notification_rules.router import (
    FORMAT,
    PERSON_PREFIX,
    RULE_PREFIX,
    decode_rule,
    encode_document,
    new_history_entry,
    public_rule,
    save_rule,
)


def sample_rule() -> RuleSpec:
    return RuleSpec.model_validate(
        {
            "name": "库存预警配置草稿",
            "event_key": "inventory_alert",
            "enabled": False,
            "condition": {
                "logic": "and",
                "groups": [
                    {
                        "logic": "and",
                        "conditions": [
                            {"field": "available_stock", "op": "lte", "value": 10},
                        ],
                    }
                ],
            },
        }
    )


def test_namespaces_separate_from_six_legacy_events() -> None:
    assert RULE_PREFIX != PERSON_PREFIX
    assert len(RULE_PREFIX + uuid4().hex) < 80
    assert not any(
        k.startswith(RULE_PREFIX) or k.startswith(PERSON_PREFIX)
        for k in (
            "inventory_alert",
            "sync_failed",
            "ads_alert",
            "approval_pending",
            "ai_completed",
            "finance_completed",
        )
    )


def test_rule_document_round_trip_and_revision() -> None:
    rule = sample_rule()
    item = new_history_entry(1, "unit_test", rule)
    data = {"format": FORMAT, "spec": rule.model_dump(mode="json"), "history": [item]}
    record = {
        "event_key": RULE_PREFIX + uuid4().hex,
        "body_template": encode_document(data),
        "version": 1,
        "updated_at": datetime.now(UTC),
    }
    doc, validated = decode_rule(record)
    assert validated["name"] == rule.name
    assert doc["history"][0]["version"] == 1
    pub = public_rule(record)
    assert pub["event_key"] == "inventory_alert"
    assert pub["enabled"] is False


def test_rule_document_corruption_is_rejected() -> None:
    item = {"event_key": RULE_PREFIX + uuid4().hex, "body_template": "{}"}
    with pytest.raises(Exception, match="RULE_STORAGE_CORRUPT|ApiError"):
        decode_rule(item)


def test_document_limit() -> None:
    with pytest.raises(Exception, match="RULE_DOCUMENT_TOO_LARGE|ApiError"):
        encode_document({"junk": "a" * 260000})


def test_activation_blocked_before_db_access() -> None:
    rule = sample_rule()
    rule.enabled = True
    with pytest.raises(Exception, match="RULE_ACTIVATION_BLOCKED|ApiError"):
        save_rule(rule, None, "admin")


def test_router_never_uses_new_tables_or_ddl() -> None:
    path = Path(__file__).resolve().parents[3] / "app/modules/notification_rules/router.py"
    code = path.read_text(encoding="utf-8")
    assert "biz_notify_" not in code
    assert "CREATE TABLE" not in code
    assert "ALTER TABLE" not in code
    assert "DROP TABLE" not in code
    assert "alembic" not in code.lower()
    assert "biz_notification_templates" in code
    assert "biz_connectors" in code


def test_person_document_does_not_store_plaintext_in_envelope() -> None:
    body = encode_document(
        {
            "format": "SZZSBJ_NO_DDL_PERSON_V2",
            "employee_key": "employee_test",
            "ciphertext": "encrypted-only",
        }
    )
    assert json.loads(body)["ciphertext"] == "encrypted-only"
    assert "feishu_open_id" not in body
