"""No production access: fake Session verifies safe transactional workflow behavior."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace as NS
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

import app.modules.keyword_planning.analysis_execution as x
from app.modules.keyword_planning.rule_gates import (
    KeywordDecision,
    KeywordEvidence,
    ProductConfirmation,
    ProductField,
)
from app.modules.keyword_planning.runtime_rules import (
    EvaluatedRun,
    KeywordInput,
    PublishedPolicy,
    VerifiedLabel,
)

PRODUCT = UUID("10000000-0000-0000-0000-000000000001")
FACT = UUID("10000000-0000-0000-0000-000000000002")
RULE = UUID("10000000-0000-0000-0000-000000000003")
RULESET = UUID("10000000-0000-0000-0000-000000000004")
TERM1 = UUID("10000000-0000-0000-0000-000000000005")
TERM2 = UUID("10000000-0000-0000-0000-000000000006")
RAW1 = UUID("10000000-0000-0000-0000-000000000007")
RAW2 = UUID("10000000-0000-0000-0000-000000000008")
UPLOAD = UUID("10000000-0000-0000-0000-000000000009")
RUN = UUID("10000000-0000-0000-0000-000000000010")
NOW = datetime(2026, 10, 23, tzinfo=UTC)


def product():
    fields = {
        field: ProductField("valid " + field, "operator")
        for field in (
            "title",
            "item_type",
            "brand",
            "material",
            "color",
            "pack",
            "size",
            "structure",
            "use",
            "owner",
        )
    }
    return ProductConfirmation("123", True, "123", fields, True, "none")


def row(keyword, rank, raw):
    return KeywordInput(
        keyword=keyword,
        source_rank=rank,
        source_row_refs=(str(raw),),
        labels=(VerifiedLabel("核心本体词", "product:verified"),),
        match=None,
        intent=None,
        root=None,
        data=None,
    )


def command(rows=None):
    candidates = rows or (
        x.ReviewedCandidate(TERM1, row("drawer organizer", 1, RAW1)),
        x.ReviewedCandidate(TERM2, row("wooden box", 2, RAW2)),
    )
    value = x.AnalysisCommand(
        source_account_ref="tenant-1",
        product_id=PRODUCT,
        product_fact_snapshot_id=FACT,
        rule_version_id=RULE,
        item_id="123",
        request_key="job-1",
        input_sha256="0" * 64,
        actor_ref="operator:1",
        engine_version="v1",
        parser_version="v1",
        normalizer_version="v1",
        source_total_rows=2,
        candidates=candidates,
    )
    return replace(value, input_sha256=x.calculate_input_sha256(value, product(), policy()))


def policy():
    return PublishedPolicy(str(RULE), "published", "tenant-1", str(PRODUCT))


class FakeSession:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.executed = []
        self.commited = False
        self.fact = NS(
            product_id=PRODUCT,
            item_id="123",
            status="confirmed",
            item_verified=True,
            confirmed_at=NOW,
            confirmed_by="owner",
            facts_sha256="b" * 64,
            missing_required_json=[],
            walmart_page_snapshot_id=None,
        )
        raw_facts = {
            name: {"value": field.value, "source": field.source, "evidence_ref": field.evidence_ref}
            for name, field in product().facts.items()
        }
        raw_facts["risk_boundary"] = {"acknowledged": True, "mode": "none"}
        self.fact.facts_with_sources_json = raw_facts
        self.fact.facts_sha256 = x._digest(raw_facts)
        config = {
            "limits": x.asdict(policy().limits),
            "confirmed_brands": {},
            "suspected_brands": {},
        }
        self.version = NS(
            status="published",
            published_at=NOW,
            published_by="owner",
            rule_set_id=RULESET,
            config_json=config,
            config_sha256=x._digest(config),
        )
        self.ruleset = NS(is_enabled=True, rule_type="scoring", scope_key="global")
        self.terms = [
            NS(id=TERM1, normalized_keyword="drawer organizer"),
            NS(id=TERM2, normalized_keyword="wooden box"),
        ]
        self.raw = [
            NS(id=RAW1, upload_id=UPLOAD, keyword_normalized="drawer organizer"),
            NS(id=RAW2, upload_id=UPLOAD, keyword_normalized="wooden box"),
        ]
        self.uploads = [NS(id=UPLOAD)]
        self._scalar_count = 0
        self._scalars_count = 0

    def begin(self):
        return nullcontext()

    def execute(self, stmt, params):
        sql = str(stmt)
        assert sql == "SELECT pg_advisory_xact_lock(:key)"
        assert isinstance(params["key"], int)
        self.executed.append((sql, params))

    def scalar(self, stmt):
        self._scalar_count += 1
        compiled = stmt.compile(dialect=postgresql.dialect())
        if self._scalar_count == 1:
            assert "request_key" in str(compiled)
            assert "tenant-1" in compiled.params.values()
            return self.existing
        assert "tenant-1" in compiled.params.values()
        return self.fact

    def get(self, model, ref):
        if model is x.AiKwRuleVersion:
            return self.version
        if model is x.AiKwRuleSet:
            return self.ruleset
        raise AssertionError("unexpected get")

    def scalars(self, stmt):
        self._scalars_count += 1
        compiled = stmt.compile(dialect=postgresql.dialect())
        if self._scalars_count == 1:
            return self.terms
        if self._scalars_count == 2:
            assert "tenant-1" in compiled.params.values()
            return self.raw
        if self._scalars_count == 3:
            assert "tenant-1" in compiled.params.values()
            return self.uploads
        if self._scalars_count == 4:
            assert "tenant-1" in compiled.params.values()
            return []
        raise AssertionError("unexpected SELECT")

    def add(self, value):
        self.added.append(value)

    def flush(self):
        if self.added and isinstance(self.added[0], x.AiKwAnalysisRun):
            self.added[0].id = RUN


def decision(keyword, score=None, grade="候选复查"):
    evidence = KeywordEvidence(
        keyword=keyword,
        primary_type="核心本体词",
        core_root=None,
        root_grade=None,
        page_coverage="页面看不出来",
        page_snapshot_verified=False,
        page_evidence_ref=None,
        match_points=None,
        intent_points=None,
        page_points=4,
        root_points=None,
        data_points=None,
        risk_points=0,
    )
    return KeywordDecision(keyword, score, grade, grade, source=evidence)


def test_persists_atomic_blocked_review_without_fabricating_scores(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr(
        x,
        "run_published_v11",
        lambda **_: EvaluatedRun(
            str(RULE), (decision("wooden box"), decision("drawer organizer")), (1, 2)
        ),
    )
    receipt = x.execute_reviewed_analysis(
        fake, command=command(), policy=policy(), product=product()
    )
    assert receipt == x.ExecutionReceipt(RUN, "blocked", True, 2)
    assert len(fake.added) == 3
    run, first, second = fake.added
    assert run.status == "blocked"
    assert run.error_code == "KW_EVIDENCE_INSUFFICIENT"
    assert first.term_id == TERM2 and second.term_id == TERM1
    assert first.score is None and second.score is None
    assert first.exact_selected is False and first.broad_selected is False
    assert first.component_evidence_json["source_row_refs"] == [str(RAW2)]
    assert first.source_account_ref == "tenant-1"


def test_existing_identical_request_is_idempotent(monkeypatch):
    fake = FakeSession(
        existing=NS(
            id=RUN,
            input_sha256=command().input_sha256,
            product_id=PRODUCT,
            rule_version_id=RULE,
            item_id="123",
            status="succeeded",
        )
    )
    monkeypatch.setattr(
        x, "run_published_v11", lambda **_: (_ for _ in ()).throw(AssertionError("must not rerun"))
    )
    receipt = x.execute_reviewed_analysis(
        fake, command=command(), policy=policy(), product=product()
    )
    assert receipt == x.ExecutionReceipt(RUN, "succeeded", False, 0)
    assert fake.added == [] and fake._scalar_count == 1


def test_idempotency_conflict_rejected_before_data_write():
    fake = FakeSession(
        existing=NS(
            id=RUN,
            input_sha256="b" * 64,
            product_id=PRODUCT,
            rule_version_id=RULE,
            item_id="123",
            status="succeeded",
        )
    )
    with pytest.raises(x.AnalysisBlocked, match="IDEMPOTENCY_KEY_REUSED"):
        x.execute_reviewed_analysis(fake, command=command(), policy=policy(), product=product())
    assert not fake.added


def test_wrong_account_rejected_before_database_access():
    fake = FakeSession()
    with pytest.raises(x.AnalysisBlocked, match="RULE_SCOPE_MISMATCH"):
        x.execute_reviewed_analysis(
            fake,
            command=command(),
            policy=replace(policy(), source_account_ref="other"),
            product=product(),
        )
    assert not fake.executed


def test_unknown_classification_origin_is_rejected_before_write():
    fake = FakeSession()
    candidates = (
        x.ReviewedCandidate(
            TERM1,
            replace(row("drawer organizer", 1, RAW1), classification_origin="untrusted"),
        ),
        x.ReviewedCandidate(TERM2, row("wooden box", 2, RAW2)),
    )
    with pytest.raises(x.AnalysisBlocked, match="CLASSIFICATION_ORIGIN_INVALID"):
        x.execute_reviewed_analysis(
            fake, command=command(candidates), policy=policy(), product=product()
        )
    assert not fake.executed


def test_bad_hash_rejected_before_database_access():
    fake = FakeSession()
    with pytest.raises(x.AnalysisBlocked, match="INPUT_HASH_INVALID"):
        x.execute_reviewed_analysis(
            fake, command=replace(command(), input_sha256="bad"), policy=policy(), product=product()
        )
    assert not fake.executed


def test_duplicate_keyword_rejected_before_database_access():
    fake = FakeSession()
    rows = (
        x.ReviewedCandidate(TERM1, row("Drawer Organizer", 1, RAW1)),
        x.ReviewedCandidate(TERM2, row("drawer organizer", 2, RAW2)),
    )
    with pytest.raises(x.AnalysisBlocked, match="DEDUPLICATED"):
        x.execute_reviewed_analysis(fake, command=command(rows), policy=policy(), product=product())
    assert not fake.executed


def test_unpublished_rule_fails_closed():
    fake = FakeSession()
    fake.version.status = "draft"
    with pytest.raises(x.AnalysisBlocked, match="RULE_VERSION_STATUS_MISMATCH"):
        x.execute_reviewed_analysis(fake, command=command(), policy=policy(), product=product())
    assert not fake.added


def test_wrong_upload_product_fails_closed():
    fake = FakeSession()
    fake.uploads = []
    with pytest.raises(x.AnalysisBlocked, match="SOURCE_UPLOAD_NOT_VERIFIED"):
        x.execute_reviewed_analysis(fake, command=command(), policy=policy(), product=product())
    assert not fake.added


def test_wrong_normalized_keyword_fails_closed():
    fake = FakeSession()
    fake.terms[0].normalized_keyword = "other"
    with pytest.raises(x.AnalysisBlocked, match="TERM_KEYWORD_MISMATCH"):
        x.execute_reviewed_analysis(fake, command=command(), policy=policy(), product=product())
    assert not fake.added


def test_invalid_source_row_reference_fails_closed():
    fake = FakeSession()
    rows = (
        x.ReviewedCandidate(TERM1, row("drawer organizer", 1, "not-a-uuid")),
        x.ReviewedCandidate(TERM2, row("wooden box", 2, RAW2)),
    )
    with pytest.raises(x.AnalysisBlocked, match="SOURCE_ROW_REFERENCE_INVALID"):
        x.execute_reviewed_analysis(fake, command=command(rows), policy=policy(), product=product())
    assert not fake.added


def test_unexpected_rule_output_does_not_write(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr(
        x,
        "run_published_v11",
        lambda **_: EvaluatedRun(
            str(RULE), (decision("invented keyword"), decision("drawer organizer")), (1, 2)
        ),
    )
    with pytest.raises(x.AnalysisBlocked, match="ANALYSIS_RESULT_KEYWORD_MISMATCH"):
        x.execute_reviewed_analysis(fake, command=command(), policy=policy(), product=product())
    assert not fake.added


def test_input_hash_binds_candidate_assessments_before_database_access():
    fake = FakeSession()
    originally = command()
    tampered = replace(
        originally,
        candidates=(
            replace(
                originally.candidates[0],
                assessment=replace(
                    originally.candidates[0].assessment,
                    exact_requested=True,
                ),
            ),
            originally.candidates[1],
        ),
    )
    with pytest.raises(x.AnalysisBlocked, match="INPUT_HASH_MISMATCH"):
        x.execute_reviewed_analysis(fake, command=tampered, policy=policy(), product=product())
    assert not fake.executed


def test_frozen_product_fact_payload_must_match_reviewed_confirmation():
    fake = FakeSession()
    fake.fact.facts_with_sources_json["title"]["value"] = "fabricated"
    fake.fact.facts_sha256 = x._digest(fake.fact.facts_with_sources_json)
    with pytest.raises(x.AnalysisBlocked, match="FROZEN_FACT_FIELD_MISMATCH"):
        x.execute_reviewed_analysis(fake, command=command(), policy=policy(), product=product())
    assert not fake.added


def test_policy_limits_must_match_frozen_rule_config():
    fake = FakeSession()
    fake.version.config_json["limits"]["max_exact"] = 999
    fake.version.config_sha256 = x._digest(fake.version.config_json)
    with pytest.raises(x.AnalysisBlocked, match="RULE_VERSION_LIMITS_MISMATCH"):
        x.execute_reviewed_analysis(fake, command=command(), policy=policy(), product=product())
    assert not fake.added


def test_account_scoped_upload_row_missing_does_not_write():
    fake = FakeSession()
    fake.raw = [fake.raw[0]]
    with pytest.raises(x.AnalysisBlocked, match="SOURCE_ROW_NOT_IN_ACCOUNT"):
        x.execute_reviewed_analysis(fake, command=command(), policy=policy(), product=product())
    assert not fake.added


def test_successful_scored_run_is_saved_as_succeeded(monkeypatch):
    fake = FakeSession()
    candidates = (
        x.ReviewedCandidate(
            TERM1,
            replace(row("drawer organizer", 1, RAW1), classification_origin="confirmed_fact"),
        ),
        x.ReviewedCandidate(
            TERM2,
            replace(row("wooden box", 2, RAW2), classification_origin="reviewed_phrase"),
        ),
    )
    monkeypatch.setattr(
        x,
        "run_published_v11",
        lambda **_: EvaluatedRun(
            str(RULE),
            (decision("drawer organizer", 92, "P0"), decision("wooden box", 80, "P1")),
            (1, 2),
        ),
    )
    receipt = x.execute_reviewed_analysis(
        fake, command=command(candidates), policy=policy(), product=product()
    )
    assert receipt.status == "succeeded" and receipt.created is True
    assert fake.added[0].summary_json["scored"] == 2
    assert fake.added[0].summary_json["automatic_evidence_count"] == 1
    assert fake.added[0].summary_json["reviewed_evidence_count"] == 1
    assert fake.added[0].summary_json["manual_review_count"] == 0
    assert fake.added[0].summary_json["official_export_authorized"] is False
    assert fake.added[1].term_id == TERM1
    assert fake.added[1].score == 92
    assert fake.added[1].decision_status == "ready"
    assert fake.added[1].component_evidence_json["classification_origin"] == "confirmed_fact"


def test_partially_scored_run_remains_blocked_for_review(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr(
        x,
        "run_published_v11",
        lambda **_: EvaluatedRun(
            str(RULE), (decision("drawer organizer", 92, "P0"), decision("wooden box")), (1, 2)
        ),
    )
    receipt = x.execute_reviewed_analysis(
        fake, command=command(), policy=policy(), product=product()
    )
    assert receipt.status == "blocked"
    run = fake.added[0]
    assert run.error_code == "KW_EVIDENCE_INSUFFICIENT"
    assert run.summary_json["scored"] == 1
    assert run.summary_json["review_required"] == 1


def test_proven_exclusion_without_score_does_not_require_review(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr(
        x,
        "run_published_v11",
        lambda **_: EvaluatedRun(
            str(RULE),
            (decision("drawer organizer", 92, "P0"), decision("wooden box", grade="不投放")),
            (1, 2),
        ),
    )
    receipt = x.execute_reviewed_analysis(
        fake, command=command(), policy=policy(), product=product()
    )
    assert receipt.status == "succeeded"
    assert fake.added[0].summary_json["review_required"] == 0


def test_market_observation_must_exist_for_the_same_scoped_term():
    from app.modules.keyword_planning.runtime_rules import MarketPoints

    fake = FakeSession()
    market = MarketPoints(8, (str(RAW1),), str(RULE), True)
    c = command()
    new_first = replace(
        c.candidates[0], assessment=replace(c.candidates[0].assessment, data=market)
    )
    cmd = command((new_first, c.candidates[1]))
    with pytest.raises(x.AnalysisBlocked, match="MARKET_EVIDENCE_MISSING_OR_CROSS_SCOPED"):
        x.execute_reviewed_analysis(fake, command=cmd, policy=policy(), product=product())
    assert not fake.added
