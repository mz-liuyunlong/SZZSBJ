"""账户管理、手工录入、招商银行 PDF。数据库部分只走隔离测试库，没配就跳过；全部合成数据。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.finance_cashflow import journal as J
from app.modules.finance_cashflow.account_schemas import (
    CashAccountCreate,
    CashAccountUpdate,
    ManualLineCreate,
)
from app.modules.finance_cashflow.accounts import (
    AccountAdminService,
    AccountRejectedError,
    clean_identity,
    ensure_cash_account,
)
from app.modules.finance_cashflow.manual_lines import (
    KIND_MANUAL_CREATE,
    ManualLineRejectedError,
    accumulate,
    apply_running_balances,
    create_manual_line,
)
from app.modules.finance_cashflow.models import (
    FinanceCashAccount,
    FinanceCashImport,
    FinanceCashLineEvent,
)
from app.modules.finance_cashflow.parsing import detector, readers
from app.modules.finance_cashflow.parsing.model import RejectFile
from app.modules.finance_cashflow.parsing.parsers import cmb
from app.modules.finance_cashflow.parsing.pipeline import parse_file
from app.modules.finance_cashflow.parsing.seed import Seed, SeedAccount, cmb_key
from app.modules.finance_cashflow.schemas import CashflowLineEventRequest
from app.modules.finance_cashflow.service import CashflowService

CMB_NO = "6200123456780042"  # 合成账号
CMB_PAGES = [
    [
        "1/2",
        "招商银行交易流水",
        "Transaction Statement of China Merchants Bank",
        "2026-10-01 -- 2026-10-31",
        "户  名：某某",
        "账号：6200********0042",
        "记账日期 货币 交易金额 联机余额 交易摘要 对手信息",
        "Date Currency Transaction",
        "Amount Balance Transaction Type Counter Party",
        "2026-10-02 CNY 1,000.00 1,000.00 汇入汇款 甲公司",
        "2026-10-03 CNY -12.50 987.50 账户管理费 个人账户管理费收入",
        "2026-10-05 CNY 0.30 987.80 账户结息 应付利息-应付个人活期存款利",
        "息(自动计提)",
    ],
    [
        "—————————",
        "温馨提示：",
        "1.交易流水验真：说明文字",
        "2/2",
        "记账日期 货币 交易金额 联机余额 交易摘要 对手信息",
        "2026-10-05 CNY -987.80 0.00 转账汇款 乙 某",
        "2026-10-06 USD 5.00 5.00 汇入汇款 丙公司",
    ],
]


def cmb_seed(with_usd: bool = True) -> Seed:
    accounts = [
        SeedAccount(
            "CMB_CNY", "招行人民币", "甲", "CNY", "对私", "cmb", "0042", {"account_no": CMB_NO}
        )
    ]
    if with_usd:
        accounts.append(
            SeedAccount(
                "CMB_USD", "招行美元", "甲", "USD", "对私", "cmb", "0042", {"account_no": CMB_NO}
            )
        )
    return Seed(accounts)


# ------------------------------------------------------------ 纯函数


def test_cmb_key_keeps_first_and_last_four():
    assert cmb_key("6200 1234 5678 0042") == "62000042"
    assert cmb_key("1234") == ""


def test_cmb_rows_join_wrapped_counterparty_and_skip_notice():
    rows = cmb.rows_of(SimpleNamespace(pdf_pages=CMB_PAGES))
    assert [r[0] for r in rows] == [
        "2026-10-02",
        "2026-10-03",
        "2026-10-05",
        "2026-10-05",
        "2026-10-06",
    ]
    assert rows[2][5] == "应付利息-应付个人活期存款利息(自动计提)"
    assert rows[3][5] == "乙 某"


def test_cmb_pdf_parses_routes_currency_and_checks_balance(monkeypatch):
    monkeypatch.setattr(readers, "read_pdf_lines", lambda content: CMB_PAGES)
    parsed = parse_file(b"%PDF-1.7 synthetic", cmb_seed())
    assert parsed.provider == "cmb"
    assert parsed.declared_range == ("2026-10-01", "2026-10-31")
    assert parsed.balance_chain_ok is True
    assert [line.account_key for line in parsed.lines].count("CMB_USD") == 1
    cny = [line for line in parsed.lines if line.account_key == "CMB_CNY"]
    assert [line.amount for line in cny] == [
        Decimal("1000"),
        Decimal("-12.5"),
        Decimal("0.3"),
        Decimal("-987.8"),
    ]
    assert len({line.line_uid for line in parsed.lines}) == 5


def test_cmb_pdf_rejects_unknown_account_or_currency(monkeypatch):
    monkeypatch.setattr(readers, "read_pdf_lines", lambda content: CMB_PAGES)
    with pytest.raises(RejectFile, match="没登记"):
        parse_file(b"%PDF-1.7", Seed([]))
    with pytest.raises(RejectFile, match="USD"):
        parse_file(b"%PDF-1.7", cmb_seed(with_usd=False))


def test_other_pdf_is_rejected(monkeypatch):
    monkeypatch.setattr(readers, "read_pdf_lines", lambda content: [["某某银行回单"]])
    with pytest.raises(RejectFile, match="只接招商银行"):
        detector.detect(b"%PDF-1.7", cmb_seed())


def test_clean_identity_per_provider():
    assert clean_identity("boc", "USD", {"inquiry_account": "1234-5678", "x": "y"}) == {
        "inquiry_account": "12345678",
        "currency": "USD",
    }
    assert clean_identity("cmb", "CNY", {"account_no": CMB_NO}) == {"account_no": CMB_NO}
    assert clean_identity("manual", "CNY", {"account_no": "1"}) == {}
    assert clean_identity("pingpong", "USD", {"user_no": "77", "main": True}) == {
        "user_no": "77",
        "main": True,
    }
    with pytest.raises(AccountRejectedError):
        clean_identity("pingpong", "USD", {"user_no": "77"})
    with pytest.raises(AccountRejectedError):
        clean_identity("payoneer", "USD", {"feature": "other"})
    with pytest.raises(AccountRejectedError):
        clean_identity("shenzhen_rural_bank", "CNY", {"account_no": "123"})


def test_accumulate_running_balance_ignores_excluded_part():
    row = SimpleNamespace
    rows = [
        row(line_uid="b", account_key="CASH", business_date=date(2026, 10, 2), file_row_order=1,
            created_at=None, amount=Decimal("-30"), exclude_amount=Decimal("30")),
        row(line_uid="a", account_key="CASH", business_date=date(2026, 10, 1), file_row_order=1,
            created_at=None, amount=Decimal("100"), exclude_amount=None),
        row(line_uid="c", account_key="CASH", business_date=date(2026, 10, 2), file_row_order=2,
            created_at=None, amount=Decimal("-20"), exclude_amount=Decimal("5")),
    ]  # fmt: skip
    assert accumulate(rows) == {"a": Decimal("100"), "b": Decimal("100"), "c": Decimal("85")}


def test_manual_line_payload_validation():
    base = dict(
        account_key="CASH", business_date=date(2026, 10, 1), direction="out", description="x"
    )
    with pytest.raises(ValidationError):
        ManualLineCreate(**base, amount=Decimal("0"))
    with pytest.raises(ValidationError):
        ManualLineCreate(**base, amount=Decimal("1.234"))
    with pytest.raises(ValidationError):
        ManualLineCreate(**{**base, "direction": "both"}, amount=Decimal("1"))


# ------------------------------------------------------------ 数据库


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        settings = Settings()  # type: ignore[call-arg]
        url = get_test_database_url(settings)
    except (SettingsError, ValidationError):
        pytest.skip("isolated PostgreSQL test database is not configured")
    engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            yield db
        transaction.rollback()
    engine.dispose()


@pytest.fixture
def service(session: Session, tmp_path: Path) -> CashflowService:
    settings = Settings()  # type: ignore[call-arg]
    settings.media_storage_root = tmp_path
    return CashflowService(session, settings)


def new_cash(session: Session) -> str:
    created = AccountAdminService(session).create(
        CashAccountCreate(
            display_name="现金", entity="甲", currency_code="CNY", kind="现金", provider="manual"
        )
    )
    return created.account_key


def manual(session: Session, key: str, amount: str, direction: str, day: date, **extra):
    return create_manual_line(
        session,
        ManualLineCreate(
            account_key=key,
            business_date=day,
            direction=direction,  # type: ignore[arg-type]
            amount=Decimal(amount),
            description=extra.pop("description", "录入"),
            **extra,
        ),
        actor="admin",
        request_id="r",
    )


def lines_of(service: CashflowService, key: str):
    items = service.list_lines(
        account_key=key, from_date=None, to_date=None, page=1, page_size=500
    ).items
    apply_running_balances(service.session, items)  # 接口层同样这么填
    return items


def test_cash_account_manual_lines_balance_review_and_exclude(service, session):
    key = new_cash(session)
    assert key == "MANUAL_CNY"
    day = date(2026, 10, 1)
    manual(session, key, "1000", "in", day, description="期初余额")
    paid = manual(session, key, "50", "out", day + timedelta(days=1), category_code="G01")
    fee = manual(session, key, "8.50", "out", day + timedelta(days=1), description="手续费",
                 category_code="F01")  # fmt: skip
    rows = {row.line_uid: row for row in lines_of(service, key)}
    assert len(rows) == 3
    assert rows[fee.line_uid].balance_after == Decimal("941.5")
    assert (rows[paid.line_uid].category_code, rows[paid.line_uid].category_source) == (
        "G01",
        "人工",
    )
    assert rows[fee.line_uid].category_code == "F01"
    assert rows[fee.line_uid].source_ref == "手工"

    passed = service.post_event(
        paid.line_uid,
        CashflowLineEventRequest(kind=J.KIND_REVIEW1_PASS, expected_version=0),
        actor="admin",
        request_id="r",
    )
    assert passed.stage == J.STAGE_OK1
    service.post_event(
        fee.line_uid,
        CashflowLineEventRequest(kind=J.KIND_EXCLUDE, reason="录错了", expected_version=0),
        actor="admin",
        request_id="r",
    )
    rows = {row.line_uid: row for row in lines_of(service, key)}
    assert rows[fee.line_uid].balance_after == Decimal("950")
    kinds = session.scalars(
        select(FinanceCashLineEvent.kind).where(FinanceCashLineEvent.line_uid == fee.line_uid)
    ).all()
    assert sorted(kinds) == sorted([KIND_MANUAL_CREATE, J.KIND_EXCLUDE])
    account = next(a for a in service.list_accounts() if a.account_key == key)
    assert (account.line_count, account.last_file_name) == (3, "手工录入")


def test_manual_line_on_bank_account_has_no_running_balance(service, session):
    created = AccountAdminService(session).create(
        CashAccountCreate(
            display_name="招行",
            entity="甲",
            currency_code="CNY",
            kind="对私",
            provider="cmb",
            identity={"account_no": CMB_NO},
        )
    )
    assert (created.account_key, created.account_no_last4) == ("CMB_CNY_0042", "0042")
    assert created.identity_fields == ["account_no"]
    made = manual(session, created.account_key, "15", "out", date(2026, 10, 3), description="年费")
    row = lines_of(service, created.account_key)[0]
    assert (row.line_uid, row.balance_after, row.amount) == (made.line_uid, None, Decimal("-15"))


def test_manual_line_rejections_and_idempotency(service, session):
    key = new_cash(session)
    first = manual(session, key, "10", "out", date(2026, 10, 1), idempotency_key="k1")
    again = manual(session, key, "10", "out", date(2026, 10, 1), idempotency_key="k1")
    assert (again.line_uid, again.replayed) == (first.line_uid, True)
    assert len(lines_of(service, key)) == 1
    with pytest.raises(ManualLineRejectedError, match="晚于今天"):
        manual(session, key, "1", "out", date.today() + timedelta(days=2))
    with pytest.raises(ManualLineRejectedError, match="类别"):
        manual(session, key, "1", "out", date(2026, 10, 1), category_code="ZZZ")
    with pytest.raises(ManualLineRejectedError) as missing:
        manual(session, "NOPE", "1", "out", date(2026, 10, 1))
    assert missing.value.status_code == 404
    AccountAdminService(session).update(key, CashAccountUpdate(is_active=False))
    with pytest.raises(ManualLineRejectedError, match="停用"):
        manual(session, key, "1", "out", date(2026, 10, 1))


def test_void_manual_batch_removes_unreviewed_line(service, session):
    key = new_cash(session)
    made = manual(session, key, "10", "out", date(2026, 10, 1))
    batch = session.scalars(
        select(FinanceCashImport).order_by(FinanceCashImport.created_at.desc())
    ).first()
    service.void_import(batch.import_id, reason="录重了", actor="admin")
    assert all(row.line_uid != made.line_uid for row in lines_of(service, key))


def test_account_admin_conflicts_and_locked_fields(service, session):
    admin = AccountAdminService(session)
    first = admin.create(
        CashAccountCreate(
            display_name="中行",
            entity="甲",
            currency_code="CNY",
            kind="对公",
            provider="boc",
            identity={"inquiry_account": "99887766"},
        )
    )
    with pytest.raises(AccountRejectedError) as dup:
        admin.create(
            CashAccountCreate(
                display_name="中行2",
                entity="甲",
                currency_code="CNY",
                kind="对公",
                provider="boc",
                identity={"inquiry_account": "99887766"},
            )
        )
    assert dup.value.status_code == 409
    usd = admin.create(
        CashAccountCreate(
            display_name="中行美元",
            entity="甲",
            currency_code="USD",
            kind="对公",
            provider="boc",
            identity={"inquiry_account": "99887766"},
        )
    )
    stored = session.get(FinanceCashAccount, usd.account_key)
    assert stored.identity_hint == {"inquiry_account": "99887766", "currency": "USD"}
    renamed = admin.update(first.account_key, CashAccountUpdate(display_name="中行人民币"))
    assert renamed.display_name == "中行人民币"
    cash = new_cash(session)
    manual(session, cash, "1", "in", date(2026, 10, 1))
    with pytest.raises(AccountRejectedError, match="已经有流水"):
        admin.update(cash, CashAccountUpdate(currency_code="USD"))
    listed = {row.account_key: row for row in admin.list_accounts()}
    assert listed[cash].line_count == 1
    assert "99887766" not in repr(listed[first.account_key])


def test_imported_cmb_lines_land_on_the_new_account(service, session, monkeypatch):
    admin = AccountAdminService(session)
    for currency in ("CNY", "USD"):
        admin.create(
            CashAccountCreate(
                display_name=f"招行{currency}",
                entity="甲",
                currency_code=currency,
                kind="对私",
                provider="cmb",
                identity={"account_no": CMB_NO},
            )
        )
    monkeypatch.setattr(readers, "read_pdf_lines", lambda content: CMB_PAGES)
    result = service.upload(
        import_id=None,
        file_name="cmb.pdf",
        content=b"%PDF-1.7 synthetic",
        actor="a",
        request_id="r",
    )
    assert result.file.status == "parsed", result.file.reject_reason
    assert sorted(result.file.account_keys) == ["CMB_CNY_0042", "CMB_USD_0042"]
    assert len(lines_of(service, "CMB_CNY_0042")) == 4


def test_ensure_cash_account_is_repeatable_and_keeps_a_stopped_one(session: Session) -> None:
    assert ensure_cash_account(session, apply=False) == "would_create"
    assert (
        session.scalars(
            select(FinanceCashAccount).where(FinanceCashAccount.display_name == "现金")
        ).first()
        is None
    )
    assert ensure_cash_account(session, apply=True) == "created"
    assert ensure_cash_account(session, apply=True) == "exists"
    rows = session.scalars(
        select(FinanceCashAccount).where(FinanceCashAccount.display_name == "现金")
    ).all()
    assert len(rows) == 1
    cash = rows[0]
    assert (cash.provider, cash.currency_code, cash.account_no_last4, cash.identity_hint) == (
        "manual",
        "CNY",
        "",
        {},
    )
    cash.is_active = False
    session.flush()
    assert ensure_cash_account(session, apply=True) == "exists"
    assert session.get(FinanceCashAccount, cash.account_key).is_active is False


def test_manual_line_only_takes_rmb_accounts(session: Session) -> None:
    usd = AccountAdminService(session).create(
        CashAccountCreate(
            display_name="美元现金",
            entity="甲",
            currency_code="USD",
            kind="现金",
            provider="manual",
        )
    )
    with pytest.raises(ManualLineRejectedError, match="只记人民币"):
        manual(session, usd.account_key, "10", "in", date(2026, 10, 1))
