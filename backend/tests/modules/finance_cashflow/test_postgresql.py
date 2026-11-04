"""数据库部分：只走 APP_ENV=test + TEST_DATABASE_URL 的隔离库；没配就跳过。全部合成数据。"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_test_database_url
from app.modules.finance_cashflow import journal as J
from app.modules.finance_cashflow.deploy_load import DeployFileError, load_deploy_data
from app.modules.finance_cashflow.models import (
    FinanceCashAccount,
    FinanceCashCategory,
    FinanceCashClassifyRule,
    FinanceCashImport,
    FinanceCashLine,
    FinanceCashLineEvent,
    FinanceCashRawFile,
)
from app.modules.finance_cashflow.schemas import CashflowLineEventRequest
from app.modules.finance_cashflow.service import (
    CashflowService,
    ImportVoidedError,
    LineNotFoundError,
    StorageNotConfiguredError,
)
from app.modules.product_management.models import ProductPricingRuleVersion
from tests.modules.finance_cashflow import synth as S
from tests.modules.finance_cashflow.test_parsing import boc_rows, eleven_account_files

BATCH_1 = UUID("00000000-0000-0000-0000-000000000001")
BATCH_2 = UUID("00000000-0000-0000-0000-000000000002")
BATCH_3 = UUID("00000000-0000-0000-0000-000000000003")


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
    for account in S.seed().accounts.values():
        session.add(
            FinanceCashAccount(
                account_key=account.account_key,
                display_name=account.display_name,
                entity=account.entity,
                currency_code=account.currency_code,
                kind=account.kind,
                provider=account.provider,
                account_no_last4=account.account_no_last4,
                identity_hint=account.match,
            )
        )
    session.flush()
    settings = Settings()  # type: ignore[call-arg]
    settings.media_storage_root = tmp_path
    return CashflowService(session, settings)


def upload(service: CashflowService, content: bytes, *, batch: UUID | None = None, name="f.xlsx"):
    return service.upload(
        import_id=batch, file_name=name, content=content, actor="admin", request_id="r"
    )


def active(service: CashflowService, account: str | None = None):
    return service.list_lines(
        account_key=account, from_date=None, to_date=None, page=1, page_size=2000
    ).items


def event(service: CashflowService, uid: str, kind: str, **fields):
    return service.post_event(
        uid, CashflowLineEventRequest(kind=kind, **fields), actor="admin", request_id="r"
    )


def test_migration_seeds_categories_and_unnamed_rules_only(session: Session):
    assert session.scalar(select(func.count()).select_from(FinanceCashCategory)) == 26
    assert session.scalar(select(func.count()).select_from(FinanceCashAccount)) == 0
    patterns = session.scalars(select(FinanceCashClassifyRule.pattern)).all()
    assert patterns
    assert {
        row.is_internal
        for row in session.scalars(
            select(FinanceCashCategory).where(FinanceCashCategory.code == "T02")
        )
    } == {True}
    assert session.get(FinanceCashCategory, "X01").is_exclude is True


def test_without_accounts_upload_is_rejected_with_reason(session: Session, tmp_path: Path):
    settings = Settings()  # type: ignore[call-arg]
    settings.media_storage_root = tmp_path
    result = CashflowService(session, settings).upload(
        import_id=None,
        file_name="b.xlsx",
        content=S.boc(S.BOC_A, boc_rows()),
        actor="admin",
        request_id=None,
    )
    assert result.file.status == "rejected"
    assert "没登记" in (result.file.reject_reason or "")


def test_upload_requires_storage_root(session: Session):
    settings = Settings()  # type: ignore[call-arg]
    settings.media_storage_root = None
    with pytest.raises(StorageNotConfiguredError):
        CashflowService(session, settings).upload(
            import_id=None, file_name="a", content=b"x", actor="admin", request_id=None
        )


def test_upload_all_formats_and_store_original(service, session, tmp_path):
    for name, content in eleven_account_files().items():
        result = upload(service, content, batch=BATCH_1, name=name)
        assert result.file.status == "parsed", result.file.reject_reason
    assert {line.account_key for line in active(service)} == set(S.seed().accounts)
    raws = session.scalars(select(FinanceCashRawFile)).all()
    assert raws
    for raw in raws:
        path = tmp_path / raw.storage_path
        assert path.read_bytes()[:2] in {b"PK", b"\xef\xbb"}
        assert raw.storage_path.startswith("finance/cashflow/")
    assert not list(tmp_path.rglob(".upload-*"))


def test_rejected_file_is_recorded_and_other_files_unaffected(service, session):
    upload(service, b"%PDF-1.4", batch=BATCH_1, name="a.pdf")
    good = upload(service, S.boc(S.BOC_A, boc_rows()), batch=BATCH_1, name="b.xlsx")
    assert good.file.status == "parsed"
    assert session.get(FinanceCashImport, BATCH_1).status == "parsed"
    statuses = {raw.file_name: raw.status for raw in session.scalars(select(FinanceCashRawFile))}
    assert statuses == {"a.pdf": "rejected", "b.xlsx": "parsed"}
    assert len(active(service, "BOC_CNY")) == 3


def test_same_file_twice_adds_nothing(service):
    content = S.boc(S.BOC_A, boc_rows())
    upload(service, content)
    again = upload(service, content, name="copy.xlsx")
    assert again.file.duplicate_of_file is True
    assert (again.file.rows_new, again.file.rows_duplicate) == (0, 3)
    assert len(active(service, "BOC_CNY")) == 3


def test_rolling_overlap_only_adds_new_lines(service, session):
    rows = boc_rows("R", 8)
    upload(service, S.boc(S.BOC_A, rows[:5]), batch=BATCH_1)
    result = upload(service, S.boc(S.BOC_A, rows[2:]), batch=BATCH_2)
    assert (result.file.rows_new, result.file.rows_duplicate) == (3, 3)
    lines = session.scalars(select(FinanceCashLine)).all()
    assert len(lines) == 8
    overlap = [line for line in lines if line.source_ref in {"R000002", "R000003", "R000004"}]
    assert all(
        line.first_import_id == BATCH_1 and line.last_import_id == BATCH_2 for line in overlap
    )


def test_void_rolls_back_and_same_file_can_be_reuploaded(service, session):
    rows = boc_rows("R", 8)
    upload(service, S.boc(S.BOC_A, rows[:5]), batch=BATCH_1)
    second = S.boc(S.BOC_A, rows[2:])
    upload(service, second, batch=BATCH_2)
    service.void_import(BATCH_2, reason="传错了", actor="admin")
    assert len(active(service, "BOC_CNY")) == 5
    remaining = session.scalars(
        select(FinanceCashLine).where(FinanceCashLine.voided_at.is_(None))
    ).all()
    assert all(line.last_import_id == BATCH_1 for line in remaining)
    assert session.get(FinanceCashImport, BATCH_2).void_reason == "传错了"
    result = upload(service, second, batch=BATCH_3)
    assert result.file.duplicate_of_file is False
    assert len(active(service, "BOC_CNY")) == 8


def test_void_three_batches_falls_back_to_middle(service, session):
    rows = boc_rows("R", 4)
    upload(service, S.boc(S.BOC_A, rows[:1]), batch=BATCH_1)
    upload(service, S.boc(S.BOC_A, rows[:2], range_=("20261001", "20261029")), batch=BATCH_2)
    upload(service, S.boc(S.BOC_A, rows[:2], range_=("20261001", "20261030")), batch=BATCH_3)
    service.void_import(BATCH_3, reason="x", actor="admin")
    first = session.scalars(
        select(FinanceCashLine).where(FinanceCashLine.source_ref == "R000000")
    ).one()
    assert (first.first_import_id, first.last_import_id) == (BATCH_1, BATCH_2)
    service.void_import(BATCH_2, reason="y", actor="admin")
    session.refresh(first)
    assert (first.first_import_id, first.last_import_id) == (BATCH_1, BATCH_1)
    second = session.scalars(
        select(FinanceCashLine).where(FinanceCashLine.source_ref == "R000001")
    ).one()
    assert second.voided_at is not None


def test_voided_batch_rejects_more_files_and_second_void(service):
    upload(service, S.boc(S.BOC_A, boc_rows()), batch=BATCH_1)
    service.void_import(BATCH_1, reason="x", actor="admin")
    with pytest.raises(ImportVoidedError):
        upload(service, S.boc(S.BOC_B, boc_rows()), batch=BATCH_1)
    with pytest.raises(ImportVoidedError):
        service.void_import(BATCH_1, reason="x", actor="admin")


def test_review_events_flow_and_append_only_history(service, session):
    upload(service, S.boc(S.BOC_A, boc_rows()))
    uid = active(service, "BOC_CNY")[0].line_uid
    first = event(service, uid, J.KIND_REVIEW1_PASS, expected_version=0)
    assert (first.stage, first.version) == (J.STAGE_OK1, 1)
    changed = event(
        service, uid, J.KIND_SET_CATEGORY, payload={"category_code": "G01"}, expected_version=1
    )
    assert (changed.stage, changed.auto_reset) == (J.STAGE_TODO, True)
    kinds = session.scalars(
        select(FinanceCashLineEvent.kind).where(FinanceCashLineEvent.line_uid == uid)
    ).all()
    assert sorted(kinds) == sorted([J.KIND_REVIEW1_PASS, J.KIND_SET_CATEGORY, J.KIND_AUTO_RESET])
    line = next(item for item in active(service, "BOC_CNY") if item.line_uid == uid)
    assert (line.category_code, line.category_source, line.stage) == ("G01", "人工", J.STAGE_TODO)


def test_stale_version_is_rejected(service):
    upload(service, S.boc(S.BOC_A, boc_rows()))
    uid = active(service, "BOC_CNY")[0].line_uid
    event(service, uid, J.KIND_REVIEW1_PASS, expected_version=0)
    with pytest.raises(J.EventRejectedError) as caught:
        event(service, uid, J.KIND_REVIEW2_PASS, expected_version=0)
    assert caught.value.status_code == 409


def test_idempotency_key_replays_without_a_second_change(service, session):
    upload(service, S.boc(S.BOC_A, boc_rows()))
    uid = active(service, "BOC_CNY")[0].line_uid
    event(service, uid, J.KIND_REVIEW1_PASS, idempotency_key="k1")
    replay = event(service, uid, J.KIND_REVIEW1_PASS, idempotency_key="k1")
    assert replay.replayed is True
    assert replay.version == 1


def test_event_on_voided_line_is_not_found(service):
    upload(service, S.boc(S.BOC_A, boc_rows()), batch=BATCH_1)
    uid = active(service, "BOC_CNY")[0].line_uid
    service.void_import(BATCH_1, reason="x", actor="admin")
    with pytest.raises(LineNotFoundError):
        event(service, uid, J.KIND_REVIEW1_PASS)


def test_review_state_survives_void_and_reimport(service):
    content = S.boc(S.BOC_A, boc_rows())
    upload(service, content, batch=BATCH_1)
    uid = active(service, "BOC_CNY")[0].line_uid
    event(service, uid, J.KIND_REVIEW1_PASS)
    service.void_import(BATCH_1, reason="x", actor="admin")
    upload(service, content, batch=BATCH_2)
    line = next(item for item in active(service, "BOC_CNY") if item.line_uid == uid)
    assert line.stage == J.STAGE_OK1


def test_line_exclusion_and_exclusion_list_anomaly(service, session):
    upload(service, S.boc(S.BOC_A, boc_rows()))
    lines = active(service, "BOC_CNY")
    event(service, lines[0].line_uid, J.KIND_EXCLUDE, reason="其他部门")
    assert (
        next(
            item for item in active(service, "BOC_CNY") if item.line_uid == lines[0].line_uid
        ).category_code
        == "X01"
    )
    assert not [item for item in service.list_anomalies() if item.type == J.ALERT_EXCLUSION]
    load_deploy_data(
        session,
        {
            "exclusions": [
                {
                    "entry_key": "e1",
                    "ref": "202610100001",
                    "amount_cny": "5",
                    "reason": "其他部门",
                    "registered_on": "2026-10-22",
                }
            ]
        },
    )
    alerts = [item for item in service.list_anomalies() if item.type == J.ALERT_EXCLUSION]
    assert len(alerts) == 1
    assert alerts[0].line_uid is None
    assert alerts[0].date == "2026-10-22"
    event(service, lines[1].line_uid, J.KIND_ATTACH_REF, payload={"ref": "202610100001"})
    assert not [item for item in service.list_anomalies() if item.type == J.ALERT_EXCLUSION]


def _load_migration():
    path = (
        Path(__file__).resolve().parents[3] / "alembic/versions/20261104_0072_finance_cashflow.py"
    )
    spec = importlib.util.spec_from_file_location("finance_cashflow_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downgrade_refuses_when_lines_exist(service, session):
    upload(service, S.boc(S.BOC_A, boc_rows()))
    context = MigrationContext.configure(session.connection())
    with Operations.context(context), pytest.raises(RuntimeError, match="has data"):
        _load_migration().downgrade()
    assert session.scalar(select(func.count()).select_from(FinanceCashLine)) == 3


def test_rules_from_seed_and_unpaired_anomaly(service):
    transfer = ("往账", "20261010", "10:00:00", "CNY", "100", "900", "某户", "", "T1", "内部调拨")
    upload(service, S.boc(S.BOC_A, [transfer]))
    line = active(service, "BOC_CNY")[0]
    assert (line.category_code, line.category_source) == ("T02", "规则")
    assert [item.type for item in service.list_anomalies()] == [J.ALERT_UNPAIRED]


def test_cny_amount_uses_month_rate(service, session):
    usd = ("来账", "20261010", "10:00:00", "USD", "10", "10", "X", "", "U1", "")
    upload(service, S.boc(S.BOC_A, [usd]))
    assert active(service, "BOC_USD")[0].amount_cny is None
    session.add(_pricing_rule(Decimal("7.2")))
    session.flush()
    assert active(service, "BOC_USD")[0].amount_cny == Decimal("72.0000")


def _pricing_rule(rate: Decimal) -> ProductPricingRuleVersion:
    return ProductPricingRuleVersion(
        source_account_ref="synthetic",
        version="v1",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        is_active=True,
        usd_cny_rate=rate,
        fx_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
        fx_source="synthetic",
        storage_month_basis_days=30,
        pricing_storage_days=30,
        suggested_gross_margin_rate=Decimal("0.3"),
        minimum_gross_margin_rate=Decimal("0.2"),
        clearance_gross_margin_rate=Decimal("0.1"),
        roi_base="purchase_cost",
        grade_a_min_margin_rate=Decimal("0.3"),
        grade_b_min_margin_rate=Decimal("0.1"),
        grade_a_min_roi=Decimal("1"),
        grade_b_min_roi=Decimal("0.5"),
        change_reason="synthetic",
        approval_ref="synthetic",
        approved_by="synthetic",
        actor_ref="synthetic",
        request_id="synthetic",
        action="create",
        status="approved",
        approved_at=datetime(2026, 1, 1, tzinfo=UTC),
        wfs_source_url="https://example.invalid",
        wfs_confirmed_at=datetime(2026, 1, 1, tzinfo=UTC),
        wfs_confirmed_by="synthetic",
        rounding_mode="none",
    )


def test_accounts_show_cover_range_and_last_file(service):
    upload(service, S.boc(S.BOC_A, boc_rows()), name="last.xlsx")
    account = next(item for item in service.list_accounts() if item.account_key == "BOC_CNY")
    assert account.line_count == 3
    assert account.last_file_name == "last.xlsx"
    assert account.cover_to.isoformat() == "2026-10-28"
    assert account.cover_source == "表头"


def test_import_list_and_detail(service):
    upload(service, S.boc(S.BOC_A, boc_rows()), batch=BATCH_1)
    data = service.list_imports(status=None, from_date=None, to_date=None, page=1, page_size=10)
    assert data.total == 1
    assert data.items[0].files[0].rows_new == 3
    assert service.get_import(BATCH_1).import_id == BATCH_1


def test_deploy_load_is_repeatable_and_validates(session: Session):
    data = {
        "accounts": [
            {
                "account_key": "K1",
                "display_name": "假账户",
                "entity": "甲",
                "currency_code": "CNY",
                "kind": "对公",
                "provider": "boc",
                "account_no_last4": "000123456789",
                "identity": {"inquiry_account": "000123456789", "currency": "CNY"},
            }
        ],
        "rules": [
            {"rule_type": "text", "pattern": "假供应商", "category_code": "C01", "sort_order": 5}
        ],
    }
    first = load_deploy_data(session, data)
    second = load_deploy_data(session, data)
    assert (first.accounts, first.rules) == (second.accounts, second.rules) == (1, 1)
    deploy_rules = session.scalars(
        select(FinanceCashClassifyRule).where(FinanceCashClassifyRule.source == "deploy")
    ).all()
    assert len(deploy_rules) == 1
    assert session.get(FinanceCashAccount, "K1").account_no_last4 == "6789"
    for bad in (
        {"accounts": [{"account_key": "K2"}]},
        {"rules": [{"rule_type": "x", "pattern": "a", "category_code": "C01", "sort_order": 1}]},
        {"rules": [{"rule_type": "text", "pattern": "(", "category_code": "C01", "sort_order": 1}]},
        {"rules": [{"rule_type": "text", "pattern": "a", "category_code": "ZZ", "sort_order": 1}]},
        {"exclusions": [{"entry_key": "e", "amount_cny": "1", "reason": "x"}]},
        {"exclusions": [{"entry_key": "e", "ref": "1", "amount_cny": "0", "reason": "x"}]},
    ):
        with pytest.raises(DeployFileError):
            load_deploy_data(session, bad)
