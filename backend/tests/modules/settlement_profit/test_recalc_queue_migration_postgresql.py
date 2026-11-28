"""迁移 0105 回滚保护（#377 终审）：还有 queued / running 的期就拒绝回滚；只剩 done 才删表。

一次性 PostgreSQL 库，从空库升级到 head 再回滚；
需要 DOMESTIC_CHAIN_DB_TESTS=1（CI 的 Domestic chain job 显式列入本文件）。
"""

from __future__ import annotations

import sqlalchemy as sa

from tests.db.domestic_postgresql_support import admin_url, create_database, drop_database
from tests.db.test_domestic_chain_postgresql import _alembic

QUEUE_0105 = "20261128_0105_settlement_recalc_queue"
BEFORE_0105 = "20261128_0104_woocommerce_products"


def test_downgrade_is_refused_while_periods_are_still_pending() -> None:
    url = admin_url()  # skips unless DOMESTIC_CHAIN_DB_TESTS=1
    database = create_database(url, "recalcqueue")
    try:
        upgraded = _alembic(url, database, "head")
        assert upgraded.returncode == 0, upgraded.stderr
        engine = sa.create_engine(url.set(database=database), hide_parameters=True)
        try:
            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "insert into settlement_recalc_queue (id, source_account_ref, store_id, "
                        "period_key, status, generation, requested_count, requested_at) values "
                        "(gen_random_uuid(), 'primary', '990000000000000001', '2026-11-03', "
                        "'queued', 1, 1, now())"
                    )
                )
            denied = _alembic(url, database, BEFORE_0105, command="downgrade")
            assert denied.returncode != 0
            assert "ROLLBACK BLOCKED" in denied.stderr + denied.stdout
            with engine.connect() as conn:
                version = conn.execute(sa.text("select version_num from alembic_version"))
                assert version.scalar_one() == QUEUE_0105
            # 算完（done）就可以回滚，表随之删掉
            with engine.begin() as conn:
                conn.execute(sa.text("update settlement_recalc_queue set status = 'done'"))
            allowed = _alembic(url, database, BEFORE_0105, command="downgrade")
            assert allowed.returncode == 0, allowed.stderr
            with engine.connect() as conn:
                gone = conn.execute(sa.text("select to_regclass('public.settlement_recalc_queue')"))
                assert gone.scalar_one() is None
        finally:
            engine.dispose()
    finally:
        drop_database(url, database)
