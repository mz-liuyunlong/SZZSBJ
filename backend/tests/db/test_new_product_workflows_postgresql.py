"""Isolated real PostgreSQL evidence for independent new-product transactions.

Opt in only on the domestic_chain_ci loopback service. Uses a disposable database
created by the test; never connects to production or any business DB.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.core.auth import Principal
from app.modules.new_product_workflow.dashboard import read_new_product_dashboard
from app.modules.new_product_workflow.purchase_plans import create_independent_purchase_plan
from app.modules.new_product_workflow.router import (
    ScoreCorrectionDecision,
    decide_score_correction,
    get_independent_purchase_plan,
)
from tests.db.domestic_postgresql_support import admin_url, create_database, drop_database
from tests.db.test_domestic_chain_postgresql import _alembic, _version

REVISION = "20261104_0075_np_corrections"
PREVIOUS = "20261104_0074_np_plans"


def _seed(engine, sku_id: UUID, workflow_id: UUID) -> None:
    interface_id = uuid4()
    sync_run_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO gov_integration_interfaces
                  (id, provider, interface_key, display_name, method,
                   endpoint_path, request_kind, handler_key, contract_version,
                   created_at, updated_at)
                VALUES
                  (:id, 'lingxing', 'synthetic-np-test', 'Synthetic NP Acceptance',
                   'POST', '/synthetic/np/test', 'offset_page',
                   'synthetic_only', 'test-v1', now(), now())
                """
            ),
            {"id": interface_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO gov_integration_sync_runs
                  (id, interface_id, provider, interface_key, source_account_ref,
                   trigger_type, status, idempotency_key, queued_at,
                   work_items_total, work_items_succeeded, work_items_failed,
                   records_seen, records_written, created_at)
                VALUES
                  (:id, :interface_id, 'lingxing', 'synthetic-np-test',
                   'synthetic-account-a', 'manual', 'succeeded',
                   'synthetic-np-idempotency', now(), 1, 1, 0, 1, 1, now())
                """
            ),
            {"id": sync_run_id, "interface_id": interface_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO dwd_lingxing_sku_identity_index
                  (id, provider, source_account_ref, lingxing_sku_id,
                   lingxing_sku_code, is_active, first_seen_run_id,
                   last_seen_run_id, first_seen_at, last_seen_at,
                   created_at, updated_at)
                VALUES
                  (:id, 'lingxing', 'synthetic-account-a', 'SYNTHETIC-001',
                   'SYNTHETIC-SKU', true, :sync_run_id, :sync_run_id,
                   now(), now(), now(), now())
                """
            ),
            {"id": sku_id, "sync_run_id": sync_run_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO product_new_workflows
                  (id, sku_identity_id, source_account_ref, status,
                   market_score, row_version)
                VALUES (:id, :sku, 'synthetic-account-a', 'scored', 8, 1)
                """
            ),
            {"id": workflow_id, "sku": sku_id},
        )


def _create_plan(engine, workflow_id: UUID, sku_id: UUID, barrier: Barrier, actor: str) -> int:
    with Session(engine) as session:
        barrier.wait(timeout=20)
        try:
            create_independent_purchase_plan(
                session,
                workflow_id=workflow_id,
                sku_identity_id=sku_id,
                source_account_ref="synthetic-account-a",
                quantity=150,
                market_score=8,
                rule_version=0,
                approval_workflow_version=2,
                approved_by=actor,
                approval_note="已人工审核通过新品内部计划",
                purchase_reason="测试业务计划并发唯一约束",
            )
            session.commit()
            return 200
        except ApiError as error:
            session.rollback()
            return error.status_code


def _decide_correction(engine, correction_id: UUID, barrier: Barrier, actor: str) -> int:
    with Session(engine) as session:
        barrier.wait(timeout=20)
        try:
            decide_score_correction(
                request=Request({"type": "http", "method": "POST", "path": "/"}),
                correction_id=correction_id,
                payload=ScoreCorrectionDecision(
                    decision="approved", note="业务日原始日志已核对且同意预估评分修正"
                ),
                session=session,
                principal=Principal(user_id=actor, permissions=frozenset()),
                accounts=frozenset({"synthetic-account-a"}),
            )
            return 200
        except ApiError as error:
            session.rollback()
            return error.status_code


def test_new_product_plan_correction_and_dashboard_postgresql() -> None:
    url = admin_url()
    database = create_database(url, "npworkflows")
    engine = None
    try:
        upgraded = _alembic(url, database, "head")
        assert upgraded.returncode == 0, upgraded.stderr
        assert _version(url, database) == [REVISION]

        engine = create_engine(url.set(database=database))
        sku_id = uuid4()
        workflow_id = uuid4()
        _seed(engine, sku_id, workflow_id)

        with Session(engine) as session:
            dashboard = read_new_product_dashboard(session, account="synthetic-account-a")
            assert dashboard["total"] == 1
            assert dashboard["formal_grade_distribution"] is None
            assert dashboard["formal_launch_success_rate"] is None
            assert dashboard["groups"]["purchase_status"][0]["name"] == "scored"
            assert read_new_product_dashboard(session, account="synthetic-account-b")["total"] == 0

        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(_create_plan, engine, workflow_id, sku_id, barrier, "a")
            second = executor.submit(_create_plan, engine, workflow_id, sku_id, barrier, "b")
            outcomes = sorted([first.result(timeout=40), second.result(timeout=40)])
        assert outcomes == [200, 409]

        with Session(engine) as session:
            count = session.scalar(
                text(
                    "SELECT count(*) FROM product_new_purchase_plans WHERE sku_identity_id = :sku"
                ),
                {"sku": sku_id},
            )
            assert count == 1
            saved = (
                session.execute(
                    text(
                        "SELECT id, snapshot_json, execution_status "
                        "FROM product_new_purchase_plans WHERE sku_identity_id = :sku"
                    ),
                    {"sku": sku_id},
                )
                .mappings()
                .one()
            )
            assert saved["execution_status"] == "not_executed"
            assert saved["snapshot_json"]["formal_score_verified"] is False
            assert saved["snapshot_json"]["creates_pmc_order"] is False

            with pytest.raises(ApiError) as denied:
                get_independent_purchase_plan(
                    request=Request({"type": "http", "method": "GET", "path": "/"}),
                    plan_id=saved["id"],
                    session=session,
                    _=Principal(user_id="other", permissions=frozenset()),
                    accounts=frozenset({"synthetic-account-b"}),
                )
            assert denied.value.status_code == 404

        correction_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO product_new_score_corrections
                      (id, workflow_id, sku_identity_id, source_account_ref,
                       dimension, from_score, requested_score, rule_version,
                       status, reason, requested_by, evidence_json)
                    VALUES
                      (:id, :workflow, :sku, 'synthetic-account-a',
                       'order', 6, 8, 0, 'pending',
                       '观察业务日完整后进行人工调整', 'operator-a',
                       CAST('{}' AS jsonb))
                    """
                ),
                {"id": correction_id, "workflow": workflow_id, "sku": sku_id},
            )
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO product_new_score_corrections
                          (id, workflow_id, sku_identity_id, source_account_ref,
                           dimension, from_score, requested_score, rule_version,
                           status, reason, requested_by, evidence_json)
                        VALUES
                          (:id, :workflow, :sku, 'synthetic-account-a',
                           'order', 7, 9, 0, 'pending',
                           '重复申请不允许','operator-b',
                           CAST('{}' AS jsonb))
                        """
                    ),
                    {"id": uuid4(), "workflow": workflow_id, "sku": sku_id},
                )

        decision_barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                _decide_correction, engine, correction_id, decision_barrier, "approver-a",
            )
            second = executor.submit(
                _decide_correction, engine, correction_id, decision_barrier, "approver-b",
            )
            outcomes = sorted([first.result(timeout=40), second.result(timeout=40)])
        assert outcomes == [200, 409]
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM product_new_score_corrections "
                    "WHERE id = :id AND status = 'approved'"
                ),
                {"id": correction_id},
            ) == 1
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM product_new_workflow_events "
                    "WHERE workflow_id = :workflow AND action = 'correction_decided'"
                ),
                {"workflow": workflow_id},
            ) == 1

        blocked = _alembic(url, database, PREVIOUS, command="downgrade")
        assert blocked.returncode != 0
        assert "NP_SCORE_CORRECTION_DOWNGRADE_BLOCKED_EXISTING_HISTORY" in blocked.stderr
        assert _version(url, database) == [REVISION]

        with engine.begin() as connection:
            connection.execute(text("DELETE FROM product_new_score_corrections"))
        downgraded = _alembic(url, database, PREVIOUS, command="downgrade")
        assert downgraded.returncode == 0, downgraded.stderr
        assert _version(url, database) == [PREVIOUS]
        repeat = _alembic(url, database, "head")
        assert repeat.returncode == 0, repeat.stderr
        assert _version(url, database) == [REVISION]

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM product_new_purchase_plans")) == 1
    finally:
        if engine is not None:
            engine.dispose()
        drop_database(url, database)
