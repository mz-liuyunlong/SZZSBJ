"""WFS 费用报表同步：期、计划、结果落地、入库货件明细。远端执行用假的，不连沃尔玛。全部合成数据。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

import tests.modules.wfs_fees.synth as S
from app.core.config import Settings, SettingsError, get_test_database_url
from app.integrations.walmart import wfs_report_engine as engine
from app.integrations.walmart.remote_dispatch import DispatchRejected
from app.modules.wfs_fees import sync_jobs as J
from app.modules.wfs_fees.models import WalmartWfsFeeLine
from app.modules.wfs_fees.report_models import WalmartWfsInboundItem, WalmartWfsReportJob
from app.modules.wfs_fees.service import WfsFeeService

STORE = J.StoreRef(S.STORE_A, "HK2612")
OTHER = J.StoreRef(S.STORE_B, "HK2613")
# 2026-10-10 08:00 UTC：09-19 ~ 10-02 这一期 10-09 上海 03:00 已经可以要了
NOW = datetime(2026, 10, 10, 8, 0, tzinfo=UTC)


# ---------------------------------------------------------------- 纯函数


def test_periods_bill_day_and_pull_time():
    assert J.period_for(date(2026, 10, 1)) == (date(2026, 9, 19), date(2026, 10, 2))
    assert J.period_for(date(2026, 8, 22)) == (date(2026, 8, 22), date(2026, 9, 4))
    assert J.pull_at(date(2026, 10, 2)) == datetime(2026, 10, 9, 3, 0, tzinfo=J.SHANGHAI)
    # 10-09 上海 03:00 = UTC 10-08 19:00：前一分钟还不到
    assert J.due_periods(datetime(2026, 10, 8, 18, 59, tzinfo=UTC)) == []
    assert J.due_periods(NOW) == [(date(2026, 9, 19), date(2026, 10, 2))]
    assert J.due_periods(datetime(2026, 11, 13, 12, 0, tzinfo=UTC)) == [
        (date(2026, 9, 19), date(2026, 10, 2)),
        (date(2026, 10, 3), date(2026, 10, 16)),
        (date(2026, 10, 17), date(2026, 10, 30)),
    ]


def test_walmart_range_and_keys_pass_the_engine_checks():
    start, end = J.walmart_range(date(2026, 10, 3), date(2026, 10, 16))
    assert (start, end) == ("2026-10-03T00:00:00.000Z", "2026-10-16T23:59:59.000Z")
    assert engine.WFS_DATE_RE.match(start) and engine.WFS_DATE_RE.match(end)
    job = WalmartWfsReportJob(
        report_type="SETTLEMENT", period_start=date(2026, 10, 3), period_end=date(2026, 10, 16)
    )
    assert engine.KEY_RE.match(J.job_key(job))


def test_plan_fetches_before_it_submits():
    waiting = WalmartWfsReportJob(
        report_type="WFS_STORAGE_FEE",
        period_start=date(2026, 9, 19),
        period_end=date(2026, 10, 2),
        status="submitted",
        request_id="req-synthetic-0001",
    )
    queued = WalmartWfsReportJob(
        report_type="SETTLEMENT",
        period_start=date(2026, 10, 3),
        period_end=date(2026, 10, 16),
        status="queued",
    )
    plan = J.WfsReportSync.build_plan(STORE, [queued, waiting])
    assert plan["store_code"] == "HK2612" and plan["max_posts"] == 2
    assert [action["op"] for action in plan["actions"]] == ["fetch", "submit"]
    assert plan["actions"][1]["dataStartTime"] == "2026-10-03T00:00:00.000Z"


# ---------------------------------------------------------------- 数据库


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        url = get_test_database_url(Settings())  # type: ignore[call-arg]
    except (SettingsError, ValidationError):
        pytest.skip("isolated PostgreSQL test database is not configured")
    db_engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
    with db_engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            yield db
        transaction.rollback()
    db_engine.dispose()


@pytest.fixture
def sync(session: Session, tmp_path: Path) -> J.WfsReportSync:
    settings = Settings()  # type: ignore[call-arg]
    settings.media_storage_root = tmp_path / "media"
    return J.WfsReportSync(session, settings)


class FakeRemote:
    """按店给出执行器结果；downloaded 的文件写进临时目录。"""

    def __init__(self, root: Path, answers):
        self.root = root
        self.answers = answers
        self.plans: list[dict] = []

    def __call__(self, store, plan):
        self.plans.append(plan)
        answer = self.answers(store, plan)
        if isinstance(answer, Exception):
            raise answer
        files = self.root / uuid4().hex / "files"
        results = []
        for item in answer:
            item = dict(item)
            content = item.pop("content", None)
            if content is not None:
                folder = files / item["key"]
                folder.mkdir(parents=True)
                (folder / "report.csv").write_bytes(content)
                item["files"] = [{"name": "report.csv"}]
            results.append(item)
        return J.RemoteRun(results, files, files.parent)


def _jobs(session, store=STORE):
    return {
        job.report_type: job
        for job in session.scalars(
            select(WalmartWfsReportJob).where(WalmartWfsReportJob.store_id == store.store_id)
        )
    }


def _run(sync, fake, now=NOW, stores=(STORE,), manual=False):
    return sync.run(list(stores), now, manual=manual, actor="tester", run_id=uuid4(), execute=fake)


def _submitted(store, plan):
    return [
        {"op": "submit", "key": a["key"], "outcome": "submitted", "requestId": f"req-{i:04d}-x"}
        for i, a in enumerate(plan["actions"])
    ]


def test_submit_then_download_imports_the_settlement(session, sync, tmp_path):
    fake = FakeRemote(tmp_path / "remote", _submitted)
    outcome = _run(sync, fake)
    assert outcome.errors == []
    jobs = _jobs(session)
    assert {job.status for job in jobs.values()} == {"submitted"}
    assert all(job.next_action_at == NOW + J.RETRY_WAIT for job in jobs.values())
    settlement = S.settlement(
        [S.fee("LostInventory", "2026-09-25", "-1.00", gtin=S.GTIN_1, ref="SYNC1")]
    )

    def later(store, plan):
        by_type = {a["reportType"]: a for a in plan["actions"]}
        assert {a["op"] for a in plan["actions"]} == {"fetch"}
        return [
            {
                "op": "fetch",
                "key": by_type["SETTLEMENT"]["key"],
                "outcome": "downloaded",
                "content": settlement,
            },
            {"op": "fetch", "key": by_type["WFS_STORAGE_FEE"]["key"], "outcome": "not_ready"},
        ]

    # 不到下次看的时间，什么都不做
    assert _run(sync, FakeRemote(tmp_path / "r0", later), now=NOW + timedelta(minutes=30))
    assert _jobs(session)["SETTLEMENT"].status == "submitted"
    _run(sync, FakeRemote(tmp_path / "r1", later), now=NOW + timedelta(hours=2))
    jobs = _jobs(session)
    assert jobs["SETTLEMENT"].status == "imported" and len(jobs["SETTLEMENT"].file_ids) == 1
    assert jobs["WFS_STORAGE_FEE"].status == "submitted" and jobs["WFS_STORAGE_FEE"].polls == 1
    line = session.scalars(select(WalmartWfsFeeLine)).one()
    assert line.store_id == STORE.store_id and line.source_ref == "SYNC1"
    # 临时目录用完删掉
    assert not any((tmp_path / "r1").iterdir())


def test_one_store_failing_does_not_stop_the_others(session, sync, tmp_path):
    def answers(store, plan):
        if store.store_code == OTHER.store_code:
            return DispatchRejected("REMOTE_UNREACHABLE")
        return _submitted(store, plan)

    outcome = _run(sync, FakeRemote(tmp_path, answers), stores=(STORE, OTHER))
    assert outcome.errors == ["HK2613:REMOTE_UNREACHABLE"]
    assert {job.status for job in _jobs(session).values()} == {"submitted"}
    other = _jobs(session, OTHER)
    assert {job.status for job in other.values()} == {"queued"}
    assert all(job.error_code == "REMOTE_UNREACHABLE" for job in other.values())


def test_schedule_leaves_failed_jobs_but_manual_sync_requeues_them(session, sync, tmp_path):
    def refused(store, plan):
        return [
            {"op": "submit", "key": a["key"], "outcome": "refused_type_not_allowed"}
            for a in plan["actions"]
        ]  # noqa: E501

    _run(sync, FakeRemote(tmp_path / "a", refused))
    assert {job.status for job in _jobs(session).values()} == {"failed"}
    fake = FakeRemote(tmp_path / "b", _submitted)
    _run(sync, fake, now=NOW + timedelta(hours=3))
    assert fake.plans == []  # 定时：失败的不再要
    _run(sync, fake, now=NOW + timedelta(hours=4), manual=True)
    statuses = sorted(job.status for job in session.scalars(select(WalmartWfsReportJob)))
    assert statuses == ["failed", "failed", "submitted", "submitted"]


def test_pii_blocked_is_final_and_nothing_is_imported(session, sync, tmp_path):
    _run(sync, FakeRemote(tmp_path / "a", _submitted))

    def blocked(store, plan):
        return [{"op": "fetch", "key": a["key"], "outcome": "pii_blocked"} for a in plan["actions"]]

    _run(sync, FakeRemote(tmp_path / "b", blocked), now=NOW + timedelta(hours=2))
    assert {job.status for job in _jobs(session).values()} == {"pii_blocked"}
    assert session.scalars(select(WalmartWfsFeeLine)).first() is None


def test_not_ready_for_too_long_fails(session, sync, tmp_path):
    _run(sync, FakeRemote(tmp_path / "a", _submitted))
    for job in _jobs(session).values():
        job.polls = J.MAX_POLLS - 1
    session.flush()

    def waiting(store, plan):
        return [{"op": "fetch", "key": a["key"], "outcome": "not_ready"} for a in plan["actions"]]

    _run(sync, FakeRemote(tmp_path / "b", waiting), now=NOW + timedelta(hours=2))
    assert {job.error_code for job in _jobs(session).values()} == {"WFS_REPORT_NOT_READY_TOO_LONG"}


def _items_csv(root: Path, store_id: str, run_id: str, rows: list[tuple[str, str, str, str, str]]):
    folder = root / "daily" / "20261010" / "walmart" / store_id / run_id
    folder.mkdir(parents=True)
    lines = ["inboundOrderId,shipmentId,gtin,sku,itemQty,receivedQty"]
    lines += [
        f"IO1,{shipment},{gtin},{sku},{qty},{received}"
        for shipment, gtin, sku, qty, received in rows
    ]  # noqa: E501
    (folder / "items.csv").write_text("﻿" + "\n".join(lines) + "\n", encoding="utf-8")


def test_inbound_items_split_the_inbound_fee_and_recognise_the_store(session, tmp_path):
    _items_csv(
        tmp_path,
        S.STORE_A,
        "wmt-synthetic-run-01",
        [(S.CARGO, S.GTIN_1, "MSKU-1", "30", "29"), (S.CARGO, S.GTIN_2, "MSKU-2", "10", "10")],
    )
    loaded = J.load_inbound_items(session, tmp_path, [S.STORE_A])
    assert loaded.rows == 2 and loaded.shipments == {S.STORE_A: {S.CARGO}}
    assert J.load_inbound_items(session, tmp_path, [S.STORE_A]).rows == 0  # 读过的 run 不再读
    assert len(session.scalars(select(WalmartWfsInboundItem)).all()) == 2
    settings = Settings()  # type: ignore[call-arg]
    settings.media_storage_root = tmp_path / "media"
    result = WfsFeeService(session, settings).upload(
        file_name="inbound.csv",
        content=S.inbound(
            [(S.CARGO, "2026-10-05", "Parcel", "Base", "$10.00")], ("2026-10-03", "2026-10-16")
        ),
        actor="tester",
        request_id=None,
    )
    # 入库运输报告没有商品：按货件号对上入库货件明细，认出店铺
    assert result.status == "parsed" and result.store_id == S.STORE_A
    parent = session.scalars(
        select(WalmartWfsFeeLine).where(WalmartWfsFeeLine.parent_line_id.is_(None))
    ).one()
    children = session.scalars(
        select(WalmartWfsFeeLine).where(WalmartWfsFeeLine.parent_line_id == parent.id)
    ).all()
    assert parent.attribution == "allocated"
    assert sorted(child.amount_usd for child in children) == [Decimal("-7.50"), Decimal("-2.50")]


def test_rate_limit_is_retried_and_never_counts_as_a_failure(session, sync, tmp_path):
    def limited(store, plan):
        return [
            {"op": "submit", "key": a["key"], "outcome": "rate_limited"} for a in plan["actions"]
        ]

    for hour in range(0, 2 * J.MAX_SUBMITS + 1, 2):
        _run(sync, FakeRemote(tmp_path / str(hour), limited), now=NOW + timedelta(hours=hour))
    jobs = _jobs(session).values()
    assert {job.status for job in jobs} == {"queued"}
    assert {job.error_code for job in jobs} == {"WFS_REPORT_RATE_LIMITED"}
    assert {job.submit_attempts for job in jobs} == {0}


# ---------------------------------------------------------------- 复审第 1 轮


def test_plan_does_not_post_again_within_the_hour():
    queued = WalmartWfsReportJob(
        report_type="SETTLEMENT",
        period_start=date(2026, 10, 3),
        period_end=date(2026, 10, 16),
        status="queued",
    )
    plan = J.WfsReportSync.build_plan(STORE, [queued], frozenset({"SETTLEMENT"}))
    assert plan["actions"][0]["post_allowed"] is False


def test_remote_unavailable_for_two_days_fails(session, sync, tmp_path):
    down = FakeRemote(tmp_path, lambda store, plan: DispatchRejected("REMOTE_UNREACHABLE"))
    for i in range(J.MAX_REMOTE_FAILURES):
        _run(sync, down, now=NOW + timedelta(hours=2 * i))
        if i == J.MAX_REMOTE_FAILURES - 2:
            assert {job.status for job in _jobs(session).values()} == {"queued"}
    jobs = _jobs(session).values()
    assert {job.status for job in jobs} == {"failed"}
    assert {job.error_code for job in jobs} == {"WFS_REPORT_REMOTE_UNAVAILABLE"}


def test_unexpected_remote_error_is_logged_not_recorded(session, sync, tmp_path):
    outcome = _run(sync, FakeRemote(tmp_path, lambda store, plan: RuntimeError("secret detail")))
    assert outcome.errors == ["HK2612:WFS_REPORT_REMOTE_FAILED"]
    assert {job.error_code for job in _jobs(session).values()} == {"WFS_REPORT_REMOTE_FAILED"}


def test_manual_sync_keeps_pii_blocked_jobs(session, sync, tmp_path):
    _run(sync, FakeRemote(tmp_path / "a", _submitted))

    def blocked(store, plan):
        return [{"op": "fetch", "key": a["key"], "outcome": "pii_blocked"} for a in plan["actions"]]

    _run(sync, FakeRemote(tmp_path / "b", blocked), now=NOW + timedelta(hours=2))
    manual = FakeRemote(tmp_path / "c", _submitted)
    _run(sync, manual, now=NOW + timedelta(hours=4), manual=True)
    assert manual.plans == []
    statuses = [job.status for job in session.scalars(select(WalmartWfsReportJob))]
    assert statuses == ["pii_blocked", "pii_blocked"]


def test_import_failure_in_one_store_does_not_stop_the_other(session, sync, tmp_path, monkeypatch):
    _run(sync, FakeRemote(tmp_path / "a", _submitted), stores=(STORE, OTHER))
    settlement = S.settlement(
        [S.fee("LostInventory", "2026-09-25", "-1.00", gtin=S.GTIN_1, ref="IMP1")]
    )

    def downloaded(store, plan):
        return [
            {"op": "fetch", "key": a["key"], "outcome": "downloaded", "content": settlement}
            if a["reportType"] == "SETTLEMENT"
            else {"op": "fetch", "key": a["key"], "outcome": "not_ready"}
            for a in plan["actions"]
        ]

    original = WfsFeeService.upload

    def upload(self, **kwargs):
        if kwargs.get("store_id") == OTHER.store_id:
            raise RuntimeError("synthetic import failure")
        return original(self, **kwargs)

    monkeypatch.setattr(WfsFeeService, "upload", upload)
    outcome = _run(
        sync,
        FakeRemote(tmp_path / "b", downloaded),
        now=NOW + timedelta(hours=2),
        stores=(STORE, OTHER),
    )
    assert outcome.errors == ["HK2613:WFS_REPORT_IMPORT_FAILED"]
    assert _jobs(session)["SETTLEMENT"].status == "imported"
    other = _jobs(session, OTHER)["SETTLEMENT"]
    assert other.status == "submitted" and other.error_code == "WFS_REPORT_IMPORT_FAILED"
    assert other.next_action_at == NOW + timedelta(hours=2) + J.RETRY_WAIT


def test_inbound_items_arriving_later_allocate_the_fee(session, sync, tmp_path):
    settings = Settings()  # type: ignore[call-arg]
    settings.media_storage_root = tmp_path / "media"
    WfsFeeService(session, settings).upload(
        file_name="inbound.csv",
        content=S.inbound(
            [(S.CARGO, "2026-10-05", "Parcel", "Base", "$10.00")], ("2026-10-03", "2026-10-16")
        ),
        actor="tester",
        request_id=None,
        store_id=S.STORE_A,
    )
    parent = session.scalars(
        select(WalmartWfsFeeLine).where(WalmartWfsFeeLine.parent_line_id.is_(None))
    ).one()
    assert parent.attribution == "unallocated"
    _items_csv(
        tmp_path / "archive",
        S.STORE_A,
        "wmt-synthetic-run-02",
        [(S.CARGO, S.GTIN_1, "MSKU-1", "30", "29"), (S.CARGO, S.GTIN_2, "MSKU-2", "10", "10")],
    )
    outcome = sync.run(
        [STORE],
        NOW,
        manual=False,
        actor="tester",
        run_id=uuid4(),
        execute=FakeRemote(tmp_path / "remote", _submitted),
        archive_root=tmp_path / "archive",
    )
    assert outcome.inbound_items == 2 and outcome.inbound_reallocated == 1
    session.refresh(parent)
    children = session.scalars(
        select(WalmartWfsFeeLine).where(WalmartWfsFeeLine.parent_line_id == parent.id)
    ).all()
    assert parent.attribution == "allocated"
    assert sum(child.amount_usd for child in children) == parent.amount_usd


def _wfs_run(session, *, trigger, status, queued_at, finished_at):
    from app.modules.integration_sync.catalog import IntegrationCatalogService
    from app.modules.integration_sync.models import IntegrationSyncRun
    from app.modules.integration_sync.repository import IntegrationSyncRepository
    from app.modules.integration_sync.wfs_report_catalog import (
        WFS_REPORT_PROVIDER,
        WFS_REPORT_SOURCE_REF,
        WFS_REPORT_SYNC_SPEC,
    )

    IntegrationCatalogService(session).bootstrap_wfs_report_governance()
    repository = IntegrationSyncRepository(session)
    interface = repository.get_interface_by_key(
        WFS_REPORT_PROVIDER, WFS_REPORT_SYNC_SPEC.interface_key
    )
    config = repository.get_config_by_scope(interface.id, WFS_REPORT_SOURCE_REF)
    run = IntegrationSyncRun(
        config_id=config.id,
        interface_id=interface.id,
        provider=WFS_REPORT_PROVIDER,
        interface_key=WFS_REPORT_SYNC_SPEC.interface_key,
        source_account_ref=WFS_REPORT_SOURCE_REF,
        trigger_type=trigger,
        status=status,
        idempotency_key=f"test:{uuid4()}",
        requested_by="tester",
        reason="test",
        queued_at=queued_at,
        finished_at=finished_at,
        error_code="SYNC_WFS_REPORTS_STORE_FAILED" if status == "failed" else None,
        work_items_total=0,
        work_items_succeeded=0,
        work_items_failed=0,
        records_seen=0,
        records_written=0,
    )
    session.add(run)
    session.flush()
    return run


def test_scheduled_partial_failure_does_not_lock_the_button(session):
    from app.modules.wfs_fees import sync_api

    now = NOW
    _wfs_run(
        session,
        trigger="schedule",
        status="failed",
        queued_at=now - timedelta(minutes=20),
        finished_at=now - timedelta(minutes=10),
    )
    state = sync_api.sync_status(session, now=now)
    assert state.status == "failed" and state.lock_reason is None
    _wfs_run(
        session,
        trigger="manual",
        status="failed",
        queued_at=now - timedelta(minutes=100),
        finished_at=now - timedelta(minutes=10),
    )
    state = sync_api.sync_status(session, now=now)
    assert state.lock_reason == "failed"
    assert state.locked_until == now - timedelta(minutes=10) + J.FAILURE_LOCK


# ---------------------------------------------------------------- 复审 P3（PR 2）


def test_submit_failed_still_blocks_another_post_within_the_hour(session, sync, tmp_path):
    def failed(store, plan):
        return [
            {"op": "submit", "key": a["key"], "outcome": "submit_failed"} for a in plan["actions"]
        ]

    _run(sync, FakeRemote(tmp_path / "a", failed))
    jobs = _jobs(session).values()
    assert {job.status for job in jobs} == {"queued"}
    assert {job.last_post_at for job in jobs} == {NOW}
    assert {job.submitted_at for job in jobs} == {None}

    # 下单失败也扣了这一小时的额度：30 分钟后手动同步，同店同类不再 POST
    # （执行器看到 post_allowed=False 就不下单，回 deferred_rate_window）
    def deferred(store, plan):
        return [
            {"op": "submit", "key": a["key"], "outcome": "deferred_rate_window"}
            for a in plan["actions"]
        ]

    again = FakeRemote(tmp_path / "b", deferred)
    _run(sync, again, now=NOW + timedelta(minutes=30), manual=True)
    assert [a["post_allowed"] for a in again.plans[0]["actions"]] == [False, False]
    assert {job.status for job in _jobs(session).values()} == {"queued"}
    # 过了 1 小时可以再下
    later = FakeRemote(tmp_path / "c", failed)
    _run(sync, later, now=NOW + timedelta(minutes=61), manual=True)
    assert [a["post_allowed"] for a in later.plans[0]["actions"]] == [True, True]


def test_reusing_an_existing_request_does_not_use_the_post_quota(session, sync, tmp_path):
    # 10-23 两期都到了：旧期复用已有请求，新期这次没轮上（执行器每类每次只下 1 单）
    now = datetime(2026, 10, 23, 8, 0, tzinfo=UTC)
    old = date(2026, 9, 19)

    def reused(store, plan):
        return [
            {"op": "submit", "key": a["key"], "outcome": "reused", "requestId": f"req-old-{i}"}
            if a["dataStartTime"].startswith(old.isoformat())
            else {"op": "submit", "key": a["key"], "outcome": "deferred_one_post_per_type_per_run"}
            for i, a in enumerate(plan["actions"])
        ]

    _run(sync, FakeRemote(tmp_path / "a", reused), now=now)
    jobs = list(session.scalars(select(WalmartWfsReportJob)))
    assert sorted(job.status for job in jobs) == ["queued", "queued", "submitted", "submitted"]
    assert {job.last_post_at for job in jobs} == {None}
    assert sync.recent_posts(STORE, now + timedelta(minutes=10)) == frozenset()
    # 10 分钟后手动同步：新期照常可以下单
    manual = FakeRemote(tmp_path / "b", _submitted)
    _run(sync, manual, now=now + timedelta(minutes=10), manual=True)
    submits = [a for a in manual.plans[0]["actions"] if a["op"] == "submit"]
    assert len(submits) == 2 and all(a["post_allowed"] for a in submits)


def test_import_failing_48_times_in_a_row_fails_the_job(session, sync, tmp_path, monkeypatch):
    _run(sync, FakeRemote(tmp_path / "a", _submitted))
    settlement = S.settlement(
        [S.fee("LostInventory", "2026-09-25", "-1.00", gtin=S.GTIN_1, ref="IMP48")]
    )

    def downloaded(store, plan):
        return [
            {"op": "fetch", "key": a["key"], "outcome": "downloaded", "content": settlement}
            for a in plan["actions"]
        ]

    def broken(self, **kwargs):
        raise RuntimeError("synthetic import failure")

    monkeypatch.setattr(WfsFeeService, "upload", broken)
    for i in range(J.MAX_IMPORT_FAILURES):
        when = NOW + timedelta(hours=2 + 2 * i)
        outcome = _run(sync, FakeRemote(tmp_path / f"r{i}", downloaded), now=when)
        assert outcome.errors == ["HK2612:WFS_REPORT_IMPORT_FAILED"]
        if i == J.MAX_IMPORT_FAILURES - 2:
            jobs = _jobs(session).values()
            assert {job.status for job in jobs} == {"submitted"}
            assert {job.import_failures for job in jobs} == {J.MAX_IMPORT_FAILURES - 1}
    assert outcome.stores[0].failed_jobs == 2 and outcome.stores[0].pending == 0
    jobs = _jobs(session).values()
    assert {job.status for job in jobs} == {"failed"}
    assert {job.error_code for job in jobs} == {"WFS_REPORT_IMPORT_FAILED"}
    assert all(job.finished_at is not None for job in jobs)
    assert session.scalars(select(WalmartWfsFeeLine)).first() is None


def test_import_failures_reset_after_a_clean_run(session, sync, tmp_path, monkeypatch):
    _run(sync, FakeRemote(tmp_path / "a", _submitted))
    original = WfsFeeService.upload

    def broken(self, **kwargs):
        raise RuntimeError("synthetic import failure")

    def downloaded(store, plan):
        return [
            {"op": "fetch", "key": a["key"], "outcome": "downloaded", "content": b"x"}
            for a in plan["actions"]
        ]

    def waiting(store, plan):
        return [{"op": "fetch", "key": a["key"], "outcome": "not_ready"} for a in plan["actions"]]

    monkeypatch.setattr(WfsFeeService, "upload", broken)
    _run(sync, FakeRemote(tmp_path / "b", downloaded), now=NOW + timedelta(hours=2))
    assert {job.import_failures for job in _jobs(session).values()} == {1}
    monkeypatch.setattr(WfsFeeService, "upload", original)
    _run(sync, FakeRemote(tmp_path / "c", waiting), now=NOW + timedelta(hours=4))
    assert {job.import_failures for job in _jobs(session).values()} == {0}


def test_reallocate_error_does_not_stop_report_import(session, sync, tmp_path, monkeypatch):
    _run(sync, FakeRemote(tmp_path / "a", _submitted), stores=(STORE, OTHER))
    _items_csv(
        tmp_path / "archive",
        S.STORE_A,
        "wmt-synthetic-run-03",
        [(S.CARGO, S.GTIN_1, "MSKU-1", "30", "29")],
    )
    settlement = S.settlement(
        [S.fee("LostInventory", "2026-09-25", "-1.00", gtin=S.GTIN_1, ref="REALLOC1")]
    )

    def downloaded(store, plan):
        return [
            {"op": "fetch", "key": a["key"], "outcome": "downloaded", "content": settlement}
            if a["reportType"] == "SETTLEMENT" and store.store_code == STORE.store_code
            else {"op": "fetch", "key": a["key"], "outcome": "not_ready"}
            for a in plan["actions"]
        ]

    def broken(self, shipments):
        raise RuntimeError("synthetic reallocate failure")

    warned: list[str] = []
    monkeypatch.setattr(WfsFeeService, "reallocate_inbound", broken)
    monkeypatch.setattr(J.logger, "warning", lambda msg, *args, **kw: warned.append(msg % args))
    outcome = sync.run(
        [STORE, OTHER],
        NOW + timedelta(hours=2),
        manual=False,
        actor="tester",
        run_id=uuid4(),
        execute=FakeRemote(tmp_path / "remote", downloaded),
        archive_root=tmp_path / "archive",
    )
    assert outcome.errors == []
    assert outcome.inbound_items == 1 and outcome.inbound_reallocated == 0
    # 货件明细已经落库，补分摊回滚
    assert len(session.scalars(select(WalmartWfsInboundItem)).all()) == 1
    # 报表照常导入，后面的店照常处理
    assert _jobs(session)["SETTLEMENT"].status == "imported"
    assert _jobs(session, OTHER)["SETTLEMENT"].polls == 1
    assert len(warned) == 1 and warned[0].startswith("wfs_inbound_reallocate_failed run_id=")


def test_oversized_zip_fails_only_that_report(session, sync, tmp_path):
    _run(sync, FakeRemote(tmp_path / "a", _submitted), stores=(STORE, OTHER))

    def answers(store, plan):
        return [
            {"op": "fetch", "key": a["key"], "outcome": "zip_too_large", "zip_limit": "total"}
            if a["reportType"] == "SETTLEMENT" and store.store_code == STORE.store_code
            else {"op": "fetch", "key": a["key"], "outcome": "not_ready"}
            for a in plan["actions"]
        ]

    later = NOW + timedelta(hours=2)
    outcome = _run(sync, FakeRemote(tmp_path / "b", answers), now=later, stores=(STORE, OTHER))
    assert outcome.errors == []
    jobs = _jobs(session)
    assert jobs["SETTLEMENT"].status == "failed"
    assert jobs["SETTLEMENT"].error_code == "WFS_REPORT_ZIP_TOO_LARGE"
    assert jobs["WFS_STORAGE_FEE"].status == "submitted"
    assert {job.status for job in _jobs(session, OTHER).values()} == {"submitted"}
    assert session.scalars(select(WalmartWfsFeeLine)).first() is None
