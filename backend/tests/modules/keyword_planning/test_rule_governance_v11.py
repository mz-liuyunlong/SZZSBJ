"""Non-I/O governance tests: approval must not be manufactured by a REST client."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from app.modules.keyword_planning.models import AiKwRuleDecision, AiKwRuleVersion
from app.modules.keyword_planning.rule_gates import ColdStartLimits
from app.modules.keyword_planning.rule_governance import (
    RuleGovernanceBlocked,
    build_draft_config,
    canonical_digest,
    create_scoring_draft,
    publish_scoring_rule,
    retire_published_rule,
    review_rule_decision,
    submit_rule_decision,
    update_scoring_draft,
)

SCORING_EDITOR = {
    "weights": {"match": 30, "intent": 20, "coverage": 20, "root": 15, "market": 15},
    "thresholds": {"p0": 85, "p1": 75, "p2": 60},
}


class DraftSession:
    def __init__(self, scope="tenant-a", rule_type="scoring"):
        self.rule_set = NS(scope_key=scope, rule_type=rule_type)
        self.versions = [1, 2]
        self.added = []
        self.flushed = 0
        self.existing = None
        self.owner = None

    def begin(self):
        return nullcontext()

    def scalar(self, stmt):
        return self.existing if self.existing is not None else self.rule_set

    def scalars(self, stmt):
        return self.versions

    def add(self, row):
        self.added.append(row)

    def flush(self):
        self.flushed += 1

    def get(self, cls, row_id):
        return self.owner


def test_draft_is_inert_and_all_eight_approvals_are_pending():
    x = build_draft_config(limits=ColdStartLimits(), confirmed_brands={}, suspected_brands={})
    assert all(v == "pending" for v in x["business_approvals"].values())
    assert len(x["business_approvals"]) == 8
    assert not x["automatic_classification_approved"]
    assert not x["official_bulk_template_approved"]
    assert x["limits"] == asdict(ColdStartLimits())


def test_config_digest_stable_across_key_order():
    assert canonical_digest({"b": 1, "a": [2]}) == canonical_digest({"a": [2], "b": 1})


@pytest.mark.parametrize(
    "confirmed,suspected",
    [
        ({"Apple": "ref:1"}, {"apple": "ref:2"}),
        ({"": "ref"}, {}),
        ({"Name": ""}, {}),
        ({"name": "r", "NAME": "r"}, {}),
    ],
)
def test_brand_proof_conflicts_fail_closed(confirmed, suspected):
    with pytest.raises(RuleGovernanceBlocked):
        build_draft_config(
            limits=ColdStartLimits(), confirmed_brands=confirmed, suspected_brands=suspected
        )


def test_normalized_brands_are_provenance_bound():
    d = build_draft_config(
        limits=ColdStartLimits(), confirmed_brands={"Multi Word": "registry:5"}, suspected_brands={}
    )
    assert d["confirmed_brands"] == {"multi word": "registry:5"}


def test_limits_bool_as_integer_rejected():
    with pytest.raises(ValueError, match="RULE_QUOTA_INVALID"):
        build_draft_config(
            limits=ColdStartLimits(max_p0=True), confirmed_brands={}, suspected_brands={}
        )


def test_limits_never_unbounded():
    with pytest.raises(RuleGovernanceBlocked, match="DRAFT_LIMIT_TOO_LARGE"):
        build_draft_config(
            limits=ColdStartLimits(max_p0=501), confirmed_brands={}, suspected_brands={}
        )


def test_create_draft_allocates_next_version_without_publishing():
    s = DraftSession()
    id = uuid4()
    result = create_scoring_draft(
        s,
        account="tenant-a",
        rule_set_id=id,
        actor="qa",
        limits=ColdStartLimits(),
        confirmed_brands={},
        suspected_brands={},
    )
    assert result.rule_set_id == id and result.version_number == 3
    assert result.status == "draft" and s.flushed == 1
    assert s.added[0].status == "draft"
    assert s.added[0].config_sha256 == canonical_digest(s.added[0].config_json)


def test_editor_config_is_persisted_without_approving_rule():
    config = build_draft_config(
        limits=ColdStartLimits(),
        confirmed_brands={},
        suspected_brands={},
        editor_config={**SCORING_EDITOR, "riskWords": "synthetic risk"},
    )
    assert config["editor_config"]["riskWords"] == "synthetic risk"
    assert config["business_approvals"]["D01"] == "pending"


def test_draft_save_rehashes_only_unsubmitted_owner_draft():
    class SaveSession(ApprovalSession):
        def scalar(self, stmt):
            if stmt.column_descriptions[0]["entity"] is AiKwRuleDecision:
                return None
            return self.version

    session = SaveSession()
    receipt = update_scoring_draft(
        session,
        account="tenant-a",
        version_id=session.version_id,
        actor="maker",
        limits=ColdStartLimits(max_p0=4),
        confirmed_brands={},
        suspected_brands={},
        editor_config=SCORING_EDITOR,
    )
    assert receipt.status == "draft"
    assert session.version.config_json["limits"]["max_p0"] == 4
    assert session.version.config_sha256 == canonical_digest(session.version.config_json)
    assert session.version.published_at is None
    session.version.status = "published"
    with pytest.raises(RuleGovernanceBlocked, match="DRAFT_NOT_EDITABLE"):
        update_scoring_draft(
            session,
            account="tenant-a",
            version_id=session.version_id,
            actor="maker",
            limits=ColdStartLimits(),
            confirmed_brands={},
            suspected_brands={},
            editor_config={},
        )


def test_cross_tenant_draft_rejected_without_write():
    s = DraftSession(scope="other")
    with pytest.raises(RuleGovernanceBlocked, match="RULE_SET_NOT_IN_ACCOUNT"):
        create_scoring_draft(
            s,
            account="tenant-a",
            rule_set_id=uuid4(),
            actor="qa",
            limits=ColdStartLimits(),
            confirmed_brands={},
            suspected_brands={},
        )
    assert not s.added


def test_other_rule_families_cannot_use_scoring_drafts():
    s = DraftSession(rule_type="ad_creation")
    with pytest.raises(RuleGovernanceBlocked, match="RULE_SET_NOT_IN_ACCOUNT"):
        create_scoring_draft(
            s,
            account="tenant-a",
            rule_set_id=uuid4(),
            actor="qa",
            limits=ColdStartLimits(),
            confirmed_brands={},
            suspected_brands={},
        )


def test_retirement_modifies_status_only():
    s = DraftSession()
    id, owner_id = uuid4(), uuid4()
    s.existing = NS(
        id=id, rule_set_id=owner_id, version_number=8, status="published", config_sha256="sha"
    )
    s.owner = NS(scope_key="tenant-a", rule_type="scoring")
    result = retire_published_rule(s, account="tenant-a", version_id=id)
    assert result.status == "retired" and s.existing.status == "retired"
    assert result.config_sha256 == "sha" and s.flushed == 1


def test_retirement_requires_owner_and_published_status():
    s = DraftSession()
    s.existing = NS(
        id=uuid4(), rule_set_id=uuid4(), version_number=1, status="published", config_sha256="sha"
    )
    s.owner = NS(scope_key="other", rule_type="scoring")
    with pytest.raises(RuleGovernanceBlocked, match="RULE_SET_NOT_IN_ACCOUNT"):
        retire_published_rule(s, account="tenant-a", version_id=s.existing.id)
    assert s.existing.status == "published"
    s.owner.scope_key = "tenant-a"
    s.existing.status = "draft"
    with pytest.raises(RuleGovernanceBlocked, match="RULE_NOT_PUBLISHED"):
        retire_published_rule(s, account="tenant-a", version_id=s.existing.id)


class ApprovalSession:
    def __init__(self):
        self.version_id = uuid4()
        self.owner = NS(
            id=uuid4(),
            scope_key="tenant-a",
            rule_type="scoring",
            created_by="maker",
            is_enabled=False,
        )
        config = {"synthetic": True}
        self.version = NS(
            id=self.version_id,
            rule_set_id=self.owner.id,
            version_number=1,
            status="draft",
            config_json=config,
            config_sha256=canonical_digest(config),
            published_by=None,
            published_at=None,
        )
        self.decisions = {}
        self.added = []

    def begin(self):
        return nullcontext()

    def scalar(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        if entity is AiKwRuleVersion:
            return self.version
        if entity is AiKwRuleDecision:
            return next(
                (row for row in self.decisions.values() if row.status == "pending_review"), None
            )
        return None

    def scalars(self, stmt):
        return list(self.decisions.values())

    def get(self, cls, row_id):
        return self.owner

    def add(self, row):
        self.added.append(row)
        if isinstance(row, AiKwRuleDecision):
            row.id = uuid4()
            self.decisions[row.decision_key] = row

    def flush(self):
        pass


def test_publish_fails_closed_until_eight_independent_reviews():
    session = ApprovalSession()
    with pytest.raises(RuleGovernanceBlocked, match="INDEPENDENT_D01_D08_APPROVAL_REQUIRED"):
        publish_scoring_rule(
            session, account="tenant-a", version_id=session.version_id, actor="publisher"
        )
    assert session.version.status == "draft"


def test_synthetic_decisions_require_separate_maker_reviewer_and_publisher():
    session = ApprovalSession()
    for index in range(1, 9):
        key = f"D{index:02d}"
        submit_rule_decision(
            session,
            account="tenant-a",
            version_id=session.version_id,
            decision_key=key,
            actor="maker",
            proposal={"strategy": "null_review"}
            if key == "D04"
            else {"choice": "synthetic-review"},
            evidence_ref="test:proposal",
        )
        # This fake picks the just submitted pending row in isolation.
        with pytest.raises(RuleGovernanceBlocked, match="INDEPENDENT_REVIEWER_REQUIRED"):
            review_rule_decision(
                session,
                account="tenant-a",
                version_id=session.version_id,
                decision_key=key,
                actor="maker",
                approved=True,
                evidence_ref="test:review",
            )
        review_rule_decision(
            session,
            account="tenant-a",
            version_id=session.version_id,
            decision_key=key,
            actor="reviewer-1" if index <= 4 else "reviewer-2",
            approved=True,
            evidence_ref="test:review",
        )
    with pytest.raises(RuleGovernanceBlocked, match="INDEPENDENT_PUBLISHER_REQUIRED"):
        publish_scoring_rule(
            session, account="tenant-a", version_id=session.version_id, actor="maker"
        )
    with pytest.raises(RuleGovernanceBlocked, match="SEPARATE_REVIEW_AND_PUBLISH_REQUIRED"):
        publish_scoring_rule(
            session, account="tenant-a", version_id=session.version_id, actor="reviewer-1"
        )
    receipt = publish_scoring_rule(
        session, account="tenant-a", version_id=session.version_id, actor="publisher"
    )
    assert receipt.status == "published" and session.owner.is_enabled
    assert session.version.config_json == {"synthetic": True}
    assert (
        len([row for row in session.added if row.__class__.__name__ == "AiKwRuleDecisionEvent"])
        == 16
    )


def test_rule_set_created_account_scoped_disabled():
    from app.modules.keyword_planning.rule_governance import create_scoring_ruleset

    s = DraftSession()
    s.rule_set = None
    record_id = create_scoring_ruleset(
        s, account="tenant-a", actor="qa", rule_key="keywords_v11", display_name=" Keywords V1.1 "
    )
    assert s.flushed == 1
    created = s.added[0]
    assert created.id == record_id and created.scope_key == "tenant-a"
    assert created.is_enabled is False and created.display_name == "Keywords V1.1"


def test_duplicate_rule_set_rejected():
    from app.modules.keyword_planning.rule_governance import create_scoring_ruleset

    s = DraftSession()
    with pytest.raises(RuleGovernanceBlocked, match="RULE_SET_ALREADY_EXISTS"):
        create_scoring_ruleset(
            s, account="tenant-a", actor="qa", rule_key="keywords_v11", display_name="Keywords V1.1"
        )
    assert not s.added


def test_global_rules_are_read_only_to_account_scope():
    s = DraftSession(scope="global")
    with pytest.raises(RuleGovernanceBlocked, match="RULE_SET_NOT_IN_ACCOUNT"):
        create_scoring_draft(
            s,
            account="tenant-a",
            rule_set_id=uuid4(),
            actor="qa",
            limits=ColdStartLimits(),
            confirmed_brands={},
            suspected_brands={},
        )
    assert not s.added
