"""Synthetic WFS Case integration verification on CI-only PostgreSQL."""

from __future__ import annotations

import os
from decimal import Decimal

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.warehouse_wfs.service import WfsFeeAlertService


def main() -> None:
    url = make_url(os.environ["DATABASE_URL"])
    if (
        os.environ.get("APP_ENV") != "dev"
        or url.database != "wfs_ci"
        or url.host not in ("127.0.0.1", "localhost")
    ):
        raise SystemExit("Synthetic Case test is restricted to isolated wfs_ci")

    with Session(create_engine(url)) as session:
        statements = [
            "create schema legacy_mirror",
            """
            create table legacy_mirror.event_wfs_fee_case (
              id bigint primary key, platform varchar(20) not null,
              store_id varchar(64) not null, store_name varchar(255) not null,
              item_id varchar(64) not null, msku varchar(128) not null,
              owner_name varchar(64) not null, manual_fee numeric(10,4) not null,
              actual_fee numeric(10,4) not null, total_units integer not null,
              est_recover numeric(12,2) not null, status varchar(16) not null,
              case_nos varchar(255) not null, reason varchar(500) not null,
              follow_log text, log_updated_at timestamp, claim_amount numeric(12,2),
              recovered_amount numeric(12,2), decided_by varchar(64) not null,
              approved_by varchar(64) not null, approved_at timestamp,
              done_at timestamp, first_alert_at timestamp,
              remark varchar(255) not null, created_at timestamp not null,
              updated_at timestamp not null
            )
            """,
            """
            create table mart_daily_sales_item_day (
              source_account_ref text, store_id text, item_id text,
              msku text, local_sku text, local_name text, title text,
              owner_ref text, business_date_la date
            )
            """,
            """
            create table dim_walmart_listings (
              source_account_ref text, store_id text, item_id text,
              msku text, local_sku text, local_name text, title text
            )
            """,
            """
            insert into mart_daily_sales_item_day
              (source_account_ref, store_id, item_id, msku, business_date_la)
            select 'synthetic-account', 'store-' || x, 'item-' || x,
              'msku-' || x, current_date
            from generate_series(1, 5) x
            """,
            """
            insert into legacy_mirror.event_wfs_fee_case
              (id, platform, store_id, store_name, item_id, msku,
               owner_name, manual_fee, actual_fee, total_units,
               est_recover, status, case_nos, reason, follow_log,
               decided_by, approved_by, remark, created_at, updated_at,
               recovered_amount, claim_amount, first_alert_at)
            select x, 'walmart', 'store-' || x, 'Synthetic Store',
              'item-' || x, 'msku-' || x, 'Synthetic Owner',
              4.0000, 6.0000, 5, 10.00,
              (array['waiting', 'following', 'approving', 'closed', 'done'])[x],
              'CS-TEST', 'Synthetic case', 'Test follow note',
              '', '', '', now(), now(),
              case when x = 5 then 1.50 else 0 end,
              10.00, now()
            from generate_series(1, 5) x
            """,
        ]
        for stmt in statements:
            session.execute(text(stmt))
        session.commit()

        service = WfsFeeAlertService(session)
        preview = service.sync_legacy_cases(execute=False)
        assert preview.legacy_total == preview.matched_identities == 5
        assert preview.will_insert == 5
        assert preview.unmatched_identities == 0
        assert preview.ambiguous_identities == 0
        assert preview.invalid_values == 0
        assert preview.case_ref_conflicts == 0

        service.sync_legacy_cases(execute=True)
        comparison = service.compare_legacy_cases()
        assert comparison.compared == comparison.matched == 5
        assert comparison.only_in_legacy == comparison.only_in_formal == 0
        assert comparison.legacy_estimated_total == comparison.formal_estimated_total
        assert comparison.legacy_recovered_total == comparison.formal_recovered_total
        assert comparison.legacy_recovered_total == Decimal("1.50")
        service.sync_legacy_cases(execute=True)
        assert session.scalar(text("select count(*) from ops_wfs_fee_anomaly_cases")) == 5

        session.execute(
            text(
                "update ops_wfs_fee_anomaly_cases "
                "set updated_by='synthetic-user', latest_follow_note='Manual saved' "
                "where legacy_case_id=1"
            )
        )
        session.commit()
        assert service.sync_legacy_cases(execute=False).protected_cases == 1
        service.sync_legacy_cases(execute=True)
        assert (
            session.scalar(
                text(
                    "select latest_follow_note from ops_wfs_fee_anomaly_cases "
                    "where legacy_case_id=1"
                )
            )
            == "Manual saved"
        )

        session.execute(
            text(
                "insert into dim_walmart_listings "
                "(source_account_ref,store_id,item_id,msku) "
                "values ('second-account','store-2','item-2','msku-2')"
            )
        )
        session.commit()
        try:
            service.sync_legacy_cases(execute=True)
        except ApiError as exc:
            assert exc.status_code == 409
            session.rollback()
        else:
            raise AssertionError("Ambiguous Case identity must block synchronization")


if __name__ == "__main__":
    main()
