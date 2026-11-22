"""Strict API contracts for user-initiated evaluation and review."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .schemas import Identity, Strict


class EvaluationCalculate(Identity):
    pass


class EvaluationReviewRequest(Identity):
    reason_type: Literal[
        "calculation_error", "scoring_basis_error", "special_exception", "manual_decision_change"
    ]
    reason: str = Field(min_length=5, max_length=4000)
    evidence: str = Field(default="", max_length=4000)
    new_decision: Literal["passed", "failed"] | None = None

    @model_validator(mode="after")
    def manual_decision_guard(self):
        if self.reason_type == "manual_decision_change":
            if self.new_decision is None or len("".join(self.reason.split())) < 20:
                raise ValueError("人工测评结论变更需明确目标结论与至少20字原因")
        elif self.new_decision is not None:
            raise ValueError("只有人工结论复核可以指定新结论")
        return self


class EvaluationReviewDecision(Strict):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=5, max_length=4000)
    expected_version: int = Field(ge=1)
