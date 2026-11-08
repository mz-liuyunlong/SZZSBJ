"""Targeted first-rule-persistence and version-conflict tests; no live DB required."""

import pytest

from app.core.api import ApiError
from app.modules.clearance import service
from app.modules.clearance.rules import ClearanceRules


class FakeSession:
    def __init__(self):
        self.statements = []
        self.commits = 0

    def execute(self, stmt, params=None):
        self.statements.append((str(stmt), params))
        return self

    def commit(self):
        self.commits += 1


def test_first_save_persists_exact_default_config_at_version_one(monkeypatch):
    monkeypatch.setattr(service, "persisted_rule_version", lambda session: None)
    session = FakeSession()
    result = service.save_rules(session, ClearanceRules(), 0, "首次保存清货规则", "operator")
    assert result == 1
    assert session.commits == 1
    inserts = [
        (sql, params)
        for sql, params in session.statements
        if "INSERT INTO biz_clearance_rule_versions" in sql
    ]
    assert len(inserts) == 1
    assert inserts[0][1]["version"] == 1
    assert inserts[0][1]["actor"] == "operator"


def test_initial_save_must_use_zero_expected_version(monkeypatch):
    monkeypatch.setattr(service, "persisted_rule_version", lambda session: None)
    session = FakeSession()
    with pytest.raises(ApiError):
        service.save_rules(session, ClearanceRules(), 1, "首次保存清货规则", "operator")
    assert session.commits == 0


def test_concurrent_save_must_not_overwrite_new_version(monkeypatch):
    monkeypatch.setattr(service, "persisted_rule_version", lambda session: (3, ClearanceRules()))
    session = FakeSession()
    with pytest.raises(ApiError):
        service.save_rules(
            session, ClearanceRules(highCoverage=240), 2, "调整清货规则：高风险售罄天数", "operator"
        )
    assert session.commits == 0
    assert not any(
        "INSERT INTO biz_clearance_rule_versions" in stmt for stmt, _ in session.statements
    )


def test_existing_identical_config_does_not_create_fake_new_version(monkeypatch):
    monkeypatch.setattr(service, "persisted_rule_version", lambda session: (4, ClearanceRules()))
    session = FakeSession()
    assert service.save_rules(session, ClearanceRules(), 4, "确认规则", "operator") == 4
    assert session.commits == 0


def test_recalculation_requires_saved_rules_before_reading_listings(monkeypatch):
    """An unsaved default must never be published as risk rule version 1."""
    monkeypatch.setattr(service, "persisted_rule_version", lambda session: None)

    class ReadOnlySource:
        def scalars(self, query):
            pytest.fail("listing facts were read before checking saved rules")

        def execute(self, stmt, params=None):
            pytest.fail("risk output was written without saved rules")

        def commit(self):
            pytest.fail("risk output was committed without saved rules")

    with pytest.raises(ApiError):
        service.recalculate_all(ReadOnlySource())
