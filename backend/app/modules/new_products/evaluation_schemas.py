"""Strict API contracts for user-initiated evaluation and review."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .schemas import Identity, Strict


class EvaluationCalculate(Identity):
    pass


class EvaluationReviewRequest(Identity):
    reason_type: Literal["calculation_error", "scoring_basis_error", "special_exception"]
    reason: str = Field(min_length=5, max_length=4000)
    evidence: str = Field(default="", max_length=4000)


class EvaluationReviewDecision(Strict):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=5, max_length=4000)
    expected_version: int = Field(ge=1)
