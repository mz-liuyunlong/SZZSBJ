"""Read-only preflight, never claims unreviewed numerical scoring is complete."""

from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import uuid4

from app.modules.keyword_planning.analysis_execution import AnalysisBlocked
from app.modules.keyword_planning.analysis_preflight import inspect_readiness


class NoWriteSession:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


def _args():
    return dict(
        account="tenant",
        product_id=uuid4(),
        item_id="123",
        fact_id=uuid4(),
        rule_version_id=uuid4(),
        upload_id=uuid4(),
        actor="qa",
    )


def test_preflight_never_declares_scoring_or_official_template_ready():
    s = NoWriteSession()
    cmd = NS(
        candidates=[
            NS(
                assessment=NS(
                    match=None,
                    intent=None,
                    root=None,
                    data=None,
                    classification_origin=(
                        "confirmed_fact"
                        if index < 20
                        else "reviewed_phrase"
                        if index < 25
                        else "manual_review"
                    ),
                )
            )
            for index in range(65)
        ]
    )
    with patch(
        "app.modules.keyword_planning.analysis_preflight.prepare_verified_analysis",
        return_value=(cmd, NS(), NS()),
    ):
        outcome = inspect_readiness(s, **_args())
    assert outcome.can_create_review_run
    assert not outcome.can_generate_scored_results
    assert not outcome.can_generate_official_upload
    assert outcome.candidate_count == 65 and outcome.top40_review_required == 40
    assert outcome.automatic_evidence_count == 20
    assert outcome.reviewed_evidence_count == 5
    assert outcome.manual_review_count == 40
    assert "KEYWORD_SCORE_EVIDENCE_REQUIRED" in outcome.review_reason_codes
    assert s.rollbacks == 1


def test_blocked_source_never_leaks_any_score_or_bypasses_review():
    s = NoWriteSession()
    with patch(
        "app.modules.keyword_planning.analysis_preflight.prepare_verified_analysis",
        side_effect=AnalysisBlocked("VERIFIED_WALMART_PAGE_REQUIRED"),
    ):
        outcome = inspect_readiness(s, **_args())
    assert not outcome.can_create_review_run
    assert outcome.review_reason_codes == ("VERIFIED_WALMART_PAGE_REQUIRED",)
    assert outcome.candidate_count == 0 and s.rollbacks == 1
    assert outcome.automatic_evidence_count == 0
    assert outcome.reviewed_evidence_count == 0
    assert outcome.manual_review_count == 0


def test_preflight_rollback_even_if_read_fails_unexpectedly():
    s = NoWriteSession()
    with patch(
        "app.modules.keyword_planning.analysis_preflight.prepare_verified_analysis",
        side_effect=RuntimeError("db temporarily unavailable"),
    ):
        try:
            inspect_readiness(s, **_args())
        except RuntimeError:
            pass
        else:
            raise AssertionError("unexpected DB exceptions must propagate")
    assert s.rollbacks == 1
