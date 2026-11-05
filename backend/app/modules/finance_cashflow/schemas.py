from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

MoneyText = Decimal


class CashflowFileResult(BaseModel):
    file_id: UUID | None = None
    file_name: str
    sha256: str
    size: int
    status: str  # parsed / rejected
    reject_reason: str | None = None
    duplicate_of_file: bool = False
    account_keys: list[str] = Field(default_factory=list)
    detected_note: str = ""
    rows_parsed: int = 0
    rows_new: int = 0
    rows_duplicate: int = 0
    declared_range_from: date | None = None
    declared_range_to: date | None = None
    balance_chain_ok: bool | None = None
    warnings: list[str] = Field(default_factory=list)


class CashflowUploadData(BaseModel):
    import_id: UUID
    file: CashflowFileResult


class CashflowImportRead(BaseModel):
    import_id: UUID
    uploader: str
    status: str
    created_at: datetime
    voided_at: datetime | None = None
    void_reason: str | None = None
    files: list[CashflowFileResult] = Field(default_factory=list)


class CashflowImportListData(BaseModel):
    items: list[CashflowImportRead]
    total: int
    page: int
    page_size: int


class CashflowVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CashflowVoidData(BaseModel):
    import_id: UUID
    lines_affected: int


class CashflowAccountRead(BaseModel):
    account_key: str
    display_name: str
    entity: str
    currency_code: str
    kind: str
    provider: str
    account_no_last4: str
    is_active: bool
    line_count: int = 0
    last_file_name: str | None = None
    cover_from: date | None = None
    cover_to: date | None = None
    cover_source: str | None = None  # 表头 / 首末笔


class CashflowCategoryRead(BaseModel):
    code: str
    big: str
    name: str
    is_internal: bool
    is_exclude: bool


class CashflowLineRead(BaseModel):
    line_uid: str
    account_key: str
    business_date: date
    month: str
    time: str | None = None
    currency_code: str
    amount: Decimal
    amount_cny: Decimal | None = None
    balance_after: Decimal | None = None
    description: str
    memo: str
    counterparty_name: str
    counterparty_account_last4: str
    source_ref: str
    file_row_order: int
    category_code: str | None = None
    category_source: str = ""
    pair_id: str | None = None
    flags: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    exclude_amount: Decimal | None = None
    exclude_reason: str | None = None
    list_excluded_cny: Decimal = Decimal("0")
    stage: str = "todo"
    stage_reason: str | None = None
    review_note: str | None = None
    version: int = 0


class CashflowLineListData(BaseModel):
    items: list[CashflowLineRead]
    total: int
    page: int
    page_size: int


class CashflowAnomalyRead(BaseModel):
    type: str
    account_key: str
    date: str
    message: str
    amount: Decimal | None = None
    # amount 的币种：剔除清单异常是 CNY，其他是流水的币种。
    currency_code: str
    line_uid: str | None = None


class CashflowLineEventRequest(BaseModel):
    kind: str = Field(max_length=32)
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=500)
    expected_version: int = Field(ge=0)
    idempotency_key: str | None = Field(default=None, max_length=128)


class CashflowLineEventData(BaseModel):
    line_uid: str
    stage: str
    stage_reason: str | None = None
    version: int
    auto_reset: bool = False
    replayed: bool = False
