# ruff: noqa: E501
"""审批单同步和自动挂单的数据库部分：只走 APP_ENV=test + TEST_DATABASE_URL 的隔离库；没配就跳过。

全部合成数据；飞书客户端是假的，不发任何网络请求。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import Settings, SettingsError, get_settings, get_test_database_url
from app.integrations.feishu_approval import FeishuApprovalError, InstancePage
from app.modules.finance_cashflow import journal as J
from app.modules.finance_cashflow.approval_service import ApprovalService
from app.modules.finance_cashflow.approval_sync import (
    ApprovalSyncNotConfiguredError,
    latest_sync,
    start_sync,
)
from app.modules.finance_cashflow.models import (
    FinanceCashAccount,
    FinanceCashApproval,
    FinanceCashImport,
    FinanceCashLine,
    FinanceCashLineEvent,
    FinanceCashLineState,
    FinanceCashRawFile,
)
from app.modules.finance_cashflow.schemas import CashflowLineEventRequest
from app.modules.finance_cashflow.service import CashflowService
from app.modules.integration_sync.catalog import IntegrationCatalogService
from app.modules.integration_sync.execution import SyncRunExecutionService
from app.modules.integration_sync.finance_approval_catalog import (
    FINANCE_APPROVAL_SOURCE_REF,
)
from app.modules.integration_sync.handlers import feishu_finance_approval_sync as handler_module
from app.modules.integration_sync.handlers.feishu_finance_approval_sync import (
    FeishuFinanceApprovalSyncHandler,
)
from app.modules.integration_sync.models import IntegrationSyncRun, IntegrationSyncRunWorkItem

SERIAL = "202610010001"
OTHER = "202610010002"
PAYMENT_CODE = "TEST-0002"
TEST_CODES = "费用报销=TEST-0001,付款申请=TEST-0002,备用金申请=TEST-0003,备用金核销=TEST-0004"
# 2026-10-01 12:00（上海时间）
START_MS = "1790827200000"
END_MS = "1790830800000"


@pytest.fixture(autouse=True)
def approval_codes(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("FINANCE_APPROVAL_CODES", TEST_CODES)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


def detail(serial=SERIAL, amount=100.0, payee="张三", status="APPROVED", reason="合成事由", **over):
    form = [
        {"name": "付款事由", "type": "textarea", "value": reason},
        {"name": "付款金额", "type": "amount", "value": amount, "ext": {"currency": "CNY"}},
        {"name": "收款人", "type": "input", "value": payee},
    ]
    return {
        "serial_number": serial,
        "status": status,
        "start_time": START_MS,
        "end_time": END_MS,
        "user_id": "u1",
        "department_id": "d1",
        "form": json.dumps(form, ensure_ascii=False),
        **over,
    }


class FakeClient:
    def __init__(self, instances=None, *, list_error=None):
        self.instances = instances or {}
        self.list_error = list_error
        self.detail_calls: list[str] = []

    def list_instances(self, *, approval_code, start_ms, end_ms, page_size, page_token):
        if self.list_error:
            raise FeishuApprovalError(self.list_error)
        assert end_ms - start_ms < 30 * 86_400_000
        # 只在第一段返回：列表是否切片在纯函数测试里验过。
        codes = [
            code
            for code, (kind_code, _detail) in self.instances.items()
            if kind_code == approval_code
        ]
        seen = getattr(self, "seen", set())
        fresh = [code for code in codes if code not in seen]
        self.seen = seen | set(fresh)
        return InstancePage(fresh, "", False)

    def get_instance(self, instance_code):
        self.detail_calls.append(instance_code)
        return self.instances[instance_code][1]

    def close(self):
        pass


def seed_line(session, uid="0123456789abcdef", amount="-100", party="张三", day=date(2026, 10, 2), memo=""):  # fmt: skip
    account_key = "ACC_TEST"
    if session.get(FinanceCashAccount, account_key) is None:
        session.add(
            FinanceCashAccount(
                account_key=account_key,
                display_name="甲",
                entity="甲",
                currency_code="CNY",
                kind="对公",
                provider="boc",
            )
        )
        session.flush()
    batch = uuid4()
    raw = uuid4()
    session.add(FinanceCashImport(import_id=batch, uploader="test"))
    session.flush()
    session.add(
        FinanceCashRawFile(
            file_id=raw,
            import_id=batch,
            file_name="f.xlsx",
            sha256=uid.ljust(64, "0"),
            size_bytes=1,
            storage_path="x",
            parser_version="v",
            status="parsed",
        )
    )
    session.flush()
    session.add(
        FinanceCashLine(
            line_uid=uid,
            account_key=account_key,
            business_date=day,
            source_timezone="Asia/Shanghai",
            amount=Decimal(amount),
            currency_code="CNY",
            counterparty_name=party,
            description="合成摘要",
            memo=memo,
            dup_ordinal=1,
            statement_row_no=1,
            file_row_order=1,
            first_import_id=batch,
            first_raw_file_id=raw,
            last_import_id=batch,
            last_raw_file_id=raw,
            parser_version="v",
        )
    )
    session.flush()
    return uid


def make_run(session, trigger="manual") -> IntegrationSyncRun:
    IntegrationCatalogService(session).bootstrap_finance_approval_governance()
    from app.modules.integration_sync.repository import IntegrationSyncRepository

    repository = IntegrationSyncRepository(session)
    interface = repository.get_interface_by_key("feishu", "financeApprovalInstances")
    config = repository.get_config_by_scope(interface.id, FINANCE_APPROVAL_SOURCE_REF)
    run = IntegrationSyncRun(
        config_id=config.id,
        interface_id=interface.id,
        provider="feishu",
        interface_key="financeApprovalInstances",
        source_account_ref=FINANCE_APPROVAL_SOURCE_REF,
        trigger_type=trigger,
        status="queued",
        idempotency_key=f"test:{uuid4()}",
        requested_by="test",
        request_id="req",
        reason="test",
        window_start=datetime(2026, 9, 1, tzinfo=UTC),
        window_end=datetime(2026, 10, 15, tzinfo=UTC),
        queued_at=datetime.now(UTC),
        work_items_total=0,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
    )
    session.add(run)
    session.flush()
    return run


def execute(session, client, run=None):
    run = run or make_run(session)
    from app.modules.integration_sync.repository import IntegrationSyncRepository

    interface = IntegrationSyncRepository(session).get_interface(run.interface_id)
    return run, FeishuFinanceApprovalSyncHandler(session, client=client).execute(run, interface)


def test_sync_writes_approval_and_run_records(session):
    client = FakeClient({"inst1": (PAYMENT_CODE, detail())})
    run, result = execute(session, client)
    assert result.status == "succeeded"
    assert run.status == "succeeded"
    assert run.records_seen == 1
    assert run.records_written == 1
    row = session.scalars(select(FinanceCashApproval)).one()
    assert row.serial_number == SERIAL
    assert row.kind == "付款申请"
    assert row.amount == Decimal("100.0000")
    assert row.applicant_user_id == "u1"
    assert row.last_run_id == run.id
    works = session.scalars(
        select(IntegrationSyncRunWorkItem).where(IntegrationSyncRunWorkItem.run_id == run.id)
    ).all()
    # 四种类型 × 两段窗口。
    assert len(works) == 8
    assert all(work.status == "succeeded" for work in works)


def test_sync_is_idempotent_and_updates_status(session):
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail(status="PENDING"))}))
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail(status="APPROVED"))}))
    row = session.scalars(select(FinanceCashApproval)).one()
    assert row.status == "APPROVED"


def test_settled_old_approvals_are_not_fetched_again(session):
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail())}))
    client = FakeClient({"inst1": (PAYMENT_CODE, detail())})
    execute(session, client)
    # 合成单子的结束时间是过去的固定日期，早于 14 天前，第二次不再取详情。
    assert client.detail_calls == []


def test_sync_failure_records_provider_code(session):
    code = "FEISHU_APPROVAL_LIST_HTTP_400_CODE_1390001"
    run, result = execute(session, FakeClient(list_error=code))
    assert result.status == "failed"
    assert run.status == "failed"
    assert run.error_code == code
    assert run.work_items_failed == 1


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "费用报销=TEST-0001",
        "费用报销=TEST-0001,付款申请=TEST-0002,备用金申请=TEST-0003,备用金核销=",
    ],
)
def test_sync_fails_with_clear_code_when_codes_are_not_configured(session, monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv("FINANCE_APPROVAL_CODES")
    else:
        monkeypatch.setenv("FINANCE_APPROVAL_CODES", raw)
    get_settings.cache_clear()
    client = FakeClient({"inst1": (PAYMENT_CODE, detail())})
    run, result = execute(session, client)
    assert result.status == "failed"
    assert run.status == "failed"
    assert run.error_code == "SYNC_FEISHU_APPROVAL_CODES_NOT_CONFIGURED"
    assert client.detail_calls == []
    assert session.scalars(select(FinanceCashApproval)).first() is None


def test_sync_refuses_disabled_interface(session):
    run = make_run(session)
    from app.modules.integration_sync.repository import IntegrationSyncRepository

    interface = IntegrationSyncRepository(session).get_interface(run.interface_id)
    interface.outbound_enabled = False
    _, result = execute(session, FakeClient(), run)
    assert result.status == "failed"
    assert run.error_code == "SYNC_FEISHU_APPROVAL_NOT_AUTHORIZED"


def test_outside_production_without_injected_client_refuses_real_calls(session, monkeypatch):
    run = make_run(session)
    from app.modules.integration_sync.repository import IntegrationSyncRepository

    interface = IntegrationSyncRepository(session).get_interface(run.interface_id)
    result = FeishuFinanceApprovalSyncHandler(session).execute(run, interface)
    assert result.status == "failed"
    assert run.error_code == "SYNC_FEISHU_APPROVAL_SERVER_ENVIRONMENT_REQUIRED"


def test_execution_service_routes_to_handler(session, monkeypatch):
    client = FakeClient({"inst1": (PAYMENT_CODE, detail())})
    monkeypatch.setattr(handler_module, "client_factory", lambda: client)
    run = make_run(session)
    SyncRunExecutionService(session).execute(run.id)
    assert run.status == "succeeded"
    assert session.scalars(select(FinanceCashApproval)).one().serial_number == SERIAL


def test_sync_auto_attaches_unique_match_and_flags_it(session):
    uid = seed_line(session)
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail())}))
    state = session.get(FinanceCashLineState, uid)
    assert state.refs == [SERIAL]
    assert state.version == 1
    assert state.stage == J.STAGE_TODO
    event = session.scalars(
        select(FinanceCashLineEvent).where(FinanceCashLineEvent.line_uid == uid)
    ).one()
    assert event.kind == J.KIND_AUTO_ATTACH_REF
    assert event.actor == "system"
    assert event.payload == {"ref": SERIAL, "by": "match"}
    read = CashflowService(session).list_lines(
        account_key=None, from_date=None, to_date=None, page=1, page_size=10
    )
    assert "自动匹配" in read.items[0].flags


def test_auto_match_is_repeatable(session):
    uid = seed_line(session)
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail())}))
    assert ApprovalService(session).auto_match() == 0
    assert session.get(FinanceCashLineState, uid).refs == [SERIAL]


def test_ambiguous_match_lists_candidates_and_attaches_nothing(session):
    uid = seed_line(session)
    execute(
        session,
        FakeClient(
            {
                "inst1": (PAYMENT_CODE, detail()),
                "inst2": (PAYMENT_CODE, detail(serial=OTHER)),
            }
        ),
    )
    assert session.get(FinanceCashLineState, uid) is None
    read = CashflowService(session).list_lines(
        account_key=None, from_date=None, to_date=None, page=1, page_size=10
    )
    assert read.items[0].approval_candidates == [OTHER, SERIAL]


def _post(session, uid, kind, payload, version):
    return CashflowService(session).post_event(
        uid,
        CashflowLineEventRequest(kind=kind, payload=payload, expected_version=version),
        actor="1",
        request_id="r",
    )


def test_detached_pair_is_not_attached_again(session):
    uid = seed_line(session)
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail())}))
    _post(session, uid, J.KIND_DETACH_REF, {"ref": SERIAL}, 1)
    assert ApprovalService(session).auto_match() == 0
    assert session.get(FinanceCashLineState, uid).refs == []


def test_reviewed_line_is_not_touched_and_not_reset(session):
    uid = seed_line(session)
    _post(session, uid, J.KIND_REVIEW1_PASS, {}, 0)
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail())}))
    state = session.get(FinanceCashLineState, uid)
    assert state.refs == []
    assert state.stage == J.STAGE_OK1


def test_serial_on_the_line_attaches_even_if_amount_differs(session):
    uid = seed_line(session, amount="-1", party="", memo=f"付款 {SERIAL}")
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail())}))
    assert session.get(FinanceCashLineState, uid).refs == [SERIAL]


def test_approval_rule_category_fills_blank_line_category(session):
    from app.modules.finance_cashflow.models import FinanceCashClassifyRule

    session.add(
        FinanceCashClassifyRule(
            rule_type="text", pattern="合成事由专用词", category_code="G02", sort_order=99999, source="seed"
        )
    )  # fmt: skip
    session.flush()
    seed_line(session)
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail(reason="合成事由专用词"))}))
    read = CashflowService(session).list_lines(
        account_key=None, from_date=None, to_date=None, page=1, page_size=10
    )
    assert read.items[0].category_code == "G02"
    assert read.items[0].category_source == J.SOURCE_APPROVAL_RULE


def _add_employee(session, feishu_user_id, feishu_name, display_name):
    session.execute(
        text(
            """
            insert into app_users (username, password_hash, is_active, created_at, updated_at,
                                   display_name, feishu_name, feishu_user_id)
            values (:username, 'synthetic', 0, now(), now(),
                    :display_name, :feishu_name, :feishu_user_id)
            """
        ),
        {
            "username": f"synthetic-{feishu_user_id}",
            "display_name": display_name,
            "feishu_name": feishu_name,
            "feishu_user_id": feishu_user_id,
        },
    )
    session.flush()


def _approval_read(session):
    return ApprovalService(session).list_approvals()[0]


def test_applicant_shows_employee_name_or_falls_back_to_id(session):
    timeline = [{"type": "PASS", "create_time": END_MS, "user_id": "u1"}]
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail(timeline=timeline))}))
    assert _approval_read(session).applicant == "u1"
    assert _approval_read(session).records[0].who == "u1"
    # 员工表后来补上这个人：不用重新同步，老单子也显示名字。
    _add_employee(session, "u1", "飞书名甲", "显示名甲")
    assert _approval_read(session).applicant == "飞书名甲"
    assert _approval_read(session).records[0].who == "飞书名甲"


def test_applicant_uses_display_name_when_feishu_name_is_blank(session):
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail())}))
    _add_employee(session, "u1", " ", "显示名甲")
    assert _approval_read(session).applicant == "显示名甲"


def test_list_approvals_reports_paid_and_unpaid(session):
    uid = seed_line(session)
    execute(
        session,
        FakeClient(
            {
                "inst1": (PAYMENT_CODE, detail()),
                "inst2": (PAYMENT_CODE, detail(serial=OTHER, amount=555.0, payee="王五")),
            }
        ),
    )
    items = {item.serial: item for item in ApprovalService(session).list_approvals()}
    assert items[SERIAL].state == "已付"
    assert items[SERIAL].status_text == "已同意"
    assert items[SERIAL].paid[0].line_uid == uid
    assert items[SERIAL].paid_sum == Decimal("100.0000")
    assert items[OTHER].state == "未付"
    assert items[OTHER].paid == []


def test_excluded_department_is_hidden_and_never_matched(session):
    seed_line(session)
    execute(session, FakeClient({"inst1": (PAYMENT_CODE, detail(department_id="d9"))}))
    # 上一步已经按默认配置挂上了：用一笔新流水验证排除部门后不再匹配，也不出现在列表里。
    settings = Settings()  # type: ignore[call-arg]
    settings.finance_approval_excluded_department_ids = "d9, d8"
    assert ApprovalService(session, settings).list_approvals() == []
    assert CashflowService(session, settings).match_approvals() == []


def test_bootstrap_is_idempotent_and_keeps_schedule_off(session):
    catalog = IntegrationCatalogService(session)
    assert catalog.bootstrap_finance_approval_governance() == ("created", "created", "created")
    assert catalog.bootstrap_finance_approval_governance()[2] == "unchanged"
    from app.modules.integration_sync.repository import IntegrationSyncRepository

    repository = IntegrationSyncRepository(session)
    interface = repository.get_interface_by_key("feishu", "financeApprovalInstances")
    config = repository.get_config_by_scope(interface.id, FINANCE_APPROVAL_SOURCE_REF)
    assert interface.outbound_enabled is True
    assert config.is_enabled is True
    assert config.schedule_enabled is False


def test_start_sync_needs_bootstrap(session):
    with pytest.raises(ApprovalSyncNotConfiguredError):
        start_sync(session, actor="1", request_id="r")


def test_start_sync_creates_run_and_does_not_double_start(session, monkeypatch):
    from app.modules.finance_cashflow import approval_sync

    dispatched = []
    monkeypatch.setattr(approval_sync, "dispatch_sync_run", dispatched.append)
    IntegrationCatalogService(session).bootstrap_finance_approval_governance()
    first = start_sync(session, actor="1", request_id="r")
    second = start_sync(session, actor="1", request_id="r2")
    assert first.status == "queued"
    assert second.run_id == first.run_id
    assert len(dispatched) == 1
    assert latest_sync(session).run_id == first.run_id


def test_latest_sync_without_runs(session):
    assert latest_sync(session).status == "never"
