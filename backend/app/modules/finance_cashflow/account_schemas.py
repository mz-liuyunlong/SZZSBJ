"""账户管理、手工录入的请求和返回。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CashAccountAdminRead(BaseModel):
    account_key: str
    display_name: str
    entity: str
    currency_code: str
    kind: str
    provider: str
    account_no_last4: str
    is_active: bool
    sort_order: int
    # 识别值（完整账号等）只写不读：这里只说有没有填、填的是哪几项。
    identity_fields: list[str] = Field(default_factory=list)
    # 数字类识别值只给尾号和位数（如 {"inquiry_account": "12 位 · 尾号 0042"}），方便核对填没填对。
    identity_tails: dict[str, str] = Field(default_factory=dict)
    pingpong_main: bool | None = None
    payoneer_feature: str | None = None
    line_count: int = 0


class CashAccountCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    entity: str = Field(min_length=1, max_length=128)
    currency_code: str
    kind: str = Field(min_length=1, max_length=16)
    provider: str
    account_no_last4: str = Field(default="", max_length=8)
    # 按平台不同：中行 inquiry_account；银座 / 招行 account_no；派安盈 feature；
    # PingPong user_no + main / account_id
    identity: dict[str, str | bool] = Field(default_factory=dict)
    sort_order: int | None = None


class CashAccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    entity: str | None = Field(default=None, min_length=1, max_length=128)
    currency_code: str | None = None
    kind: str | None = Field(default=None, min_length=1, max_length=16)
    provider: str | None = None
    account_no_last4: str | None = Field(default=None, max_length=8)
    # 不传 = 不改；传了就整组替换
    identity: dict[str, str | bool] | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class ManualLineCreate(BaseModel):
    account_key: str
    business_date: date
    direction: Literal["in", "out"]
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    description: str = Field(min_length=1, max_length=500)
    counterparty_name: str = Field(default="", max_length=200)
    memo: str = Field(default="", max_length=500)
    category_code: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class ManualLineCreated(BaseModel):
    line_uid: str
    account_key: str
    replayed: bool = False
