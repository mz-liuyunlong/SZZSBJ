# ruff: noqa: E501, E402, UP031
"""账户主数据（dim_finance_cash_accounts 种子）。完整识别值只在本地种子文件 / 仓库 migration 种子里，不写进文档。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

ACCOUNT_KEYS_V1 = (
    "BOC_CNY",
    "BOC_USD",
    "ZSBJ_BOC",
    "ZSBJ_BOC_USD",
    "ZSBJ_YZ",
    "PAYONEER",
    "PAYONEER_FH",
    "WORLDFIRST",
    "PINGPONG_MAIN_USD",
    "PINGPONG_MAIN_CNH",
    "PINGPONG_STORE_A",
)


@dataclass
class SeedAccount:
    account_key: str
    display_name: str
    entity: str
    currency_code: str
    kind: str
    provider: str
    account_no_last4: str = ""
    match: dict = field(default_factory=dict)
    is_active: bool = True


class Seed:
    def __init__(self, accounts: list[SeedAccount]) -> None:
        self.accounts = {a.account_key: a for a in accounts}

    @classmethod
    def from_json(cls, path):
        data = json.load(open(path, encoding="utf-8"))
        return cls([SeedAccount(**a) for a in data["accounts"]])

    def _active(self, provider):
        return [a for a in self.accounts.values() if a.provider == provider and a.is_active]

    def boc(self, inquiry: str, currency: str):
        for a in self._active("boc"):
            if a.match.get("inquiry_account") == inquiry and a.match.get("currency") == currency:
                return a
        return None

    def boc_known_inquiry(self, inquiry: str) -> bool:
        return any(a.match.get("inquiry_account") == inquiry for a in self._active("boc"))

    def yz(self, account_no: str):
        return next(
            (
                a
                for a in self._active("shenzhen_rural_bank")
                if a.match.get("account_no") == account_no
            ),
            None,
        )

    def payoneer(self, feature: str):
        return next(
            (a for a in self._active("payoneer") if a.match.get("feature") == feature), None
        )

    def worldfirst(self):
        return next(iter(self._active("worldfirst")), None)

    def pp_user_nos(self):
        return {a.match.get("user_no") for a in self._active("pingpong")}

    def pp_main(self, user_no: str, currency: str):
        return next(
            (
                a
                for a in self._active("pingpong")
                if a.match.get("main")
                and a.match.get("user_no") == user_no
                and a.currency_code == currency
            ),
            None,
        )

    def pp_store(self, account_id: str):
        return next(
            (a for a in self._active("pingpong") if a.match.get("account_id") == account_id), None
        )

    def cmb(self, key: str, currency: str):
        """招商银行：PDF 里账号只露前 4 后 4 位，按这 8 位 + 币种认账户。"""
        return next(
            (
                a
                for a in self._active("cmb")
                if cmb_key(a.match.get("account_no", "")) == key and a.currency_code == currency
            ),
            None,
        )

    def cmb_known(self, key: str) -> bool:
        return any(cmb_key(a.match.get("account_no", "")) == key for a in self._active("cmb"))


def cmb_key(account_no: str) -> str:
    digits = "".join(ch for ch in str(account_no) if ch.isdigit())
    return digits[:4] + digits[-4:] if len(digits) >= 8 else ""
