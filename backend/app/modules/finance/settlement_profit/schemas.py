"""Request / response models of the settlement profit write API (PRP §7)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_REVIEW_LINES = 500
BATCH_CONFIRM_THRESHOLD = 20  # PRP §5: 批量 ≥ 20 行 → confirm_token

Text = Field(min_length=1, max_length=2000)


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdjustmentCreate(_Body):
    kind: Literal["cost", "amount", "assign_item", "assign_store", "note"]
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = Text
    expected_version: int = Field(ge=1)


class RevokeRequest(_Body):
    reason: str = Text
    expected_version: int = Field(ge=1)


class ReviewRequest(_Body):
    line_ids: list[UUID] = Field(min_length=1, max_length=MAX_REVIEW_LINES)
    stage: Literal["first", "final"]
    decision: Literal["pass", "reject"]
    comment: str | None = Field(default=None, max_length=2000)
    expected_versions: dict[str, int]
    confirm_token: str | None = Field(default=None, max_length=64)


class CloseRequest(_Body):
    store_ids: list[str] | Literal["ALL"]
    confirm_token: str = Field(min_length=1, max_length=64)


class ReopenRequest(_Body):
    store_ids: list[str] | Literal["ALL"]
    reason: str = Text
    confirm_token: str = Field(min_length=1, max_length=64)


class NetProfitConfigUpdate(_Body):
    effective_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    fixed_cny: str = Field(pattern=r"^\d{1,14}(\.\d{1,4})?$")
    excluded_owner_ids: list[str] = Field(default_factory=list, max_length=200)
    expected_version: int = Field(ge=0)  # 0: the effective month has no setting yet
    reason: str | None = Field(default=None, max_length=2000)
    confirm_token: str = Field(min_length=1, max_length=64)


# ------------------------------------------------------------------ responses


class MoneyOut(BaseModel):
    amount: str
    currency_code: str


class AdjustmentOut(BaseModel):
    id: str
    line_key: str
    store_id: str
    store_label: str
    month: str
    kind: str
    payload: dict[str, Any]
    reason: str
    status: str
    version: int
    actor_id: str
    actor_role: str
    acted_at: str
    revoked_by: str | None
    revoked_at: str | None
    revoke_reason: str | None


class LineState(BaseModel):
    line_id: str
    status: str
    version: int


class Recalc(BaseModel):
    """Recalculation after a write (PRP §8.9).

    ``deferred``: queued for the month recalculation, which runs once the database
    loader for settlement lines is on main; the line version above is already new.
    """

    status: Literal["done", "deferred"]
    month: str
    store_ids: list[str]


class AdjustmentResult(BaseModel):
    adjustment: AdjustmentOut
    line: LineState
    recalc: Recalc


class ReviewLineResult(BaseModel):
    line_id: str
    ok: bool
    code: str | None = None
    status: str | None = None
    version: int | None = None


class ReviewResult(BaseModel):
    stage: str
    decision: str
    results: list[ReviewLineResult]
    succeeded: int
    failed: int


class MonthCloseOut(BaseModel):
    store_id: str
    month: str
    status: str
    frozen_calc_version: int | None
    snapshot_totals: dict[str, Any] | None
    reopen_reason: str | None
    version: int


class MonthCloseResult(BaseModel):
    month: str
    rows: list[MonthCloseOut]
    recalc: Recalc | None = None


class NetProfitConfigOut(BaseModel):
    effective_month: str | None
    requested_month: str
    fixed_cny: MoneyOut
    excluded_owner_ids: list[str]
    version: int
    is_default: bool


class NetProfitConfigResult(BaseModel):
    config: NetProfitConfigOut
    recalc: Recalc


class WriteMeta(BaseModel):
    source: str
    idempotent_replay: bool
    write_id: str
