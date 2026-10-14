"""formalize WFS fee anomaly cases

Revision ID: 20261014_0030_formalize_wfs_fee_cases
Revises: 20261006_0029_legacy_selected_mirror_tables
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20261014_0030_formalize_wfs_fee_cases"
down_revision: str | Sequence[str] | None = "20261006_0029_legacy_selected_mirror_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute(statement: str) -> None:
    op.get_bind().execute(text(statement))


def upgrade() -> None:
    _execute(
        """
        do $$
        begin
          if to_regclass('public.ops_wfs_fee_anomaly_cases') is not null
             and to_regclass('public.ops_wfs_fee_anomaly_cases_legacy_shape_backup') is null then
            alter table public.ops_wfs_fee_anomaly_cases
              rename to ops_wfs_fee_anomaly_cases_legacy_shape_backup;
          end if;
        end $$;
        """
    )

    _execute(
        """
        create table if not exists public.ops_wfs_fee_anomaly_cases (
            id uuid primary key,

            source_kind varchar(32) not null default 'legacy_mirror',
            source_case_ref varchar(255) unique,
            legacy_case_id bigint,
            legacy_status varchar(32),
            legacy_updated_at timestamp,
            last_mirrored_at timestamptz,
            sync_hash varchar(64),

            platform varchar(32) not null default 'walmart',
            source_account_ref varchar(128) not null,
            store_id varchar(128) not null,
            item_id varchar(128) not null,
            msku text not null,
            store_name_snapshot varchar(255),
            local_sku_snapshot text,
            product_name_snapshot text,
            owner_ref varchar(128),
            owner_name_snapshot varchar(128),

            currency_code varchar(3) not null default 'USD',
            manual_unit_fee numeric(12,4) not null,
            actual_unit_fee numeric(12,4) not null,
            unit_fee_diff numeric(12,4) not null,
            fee_source varchar(64) not null default 'legacy_case',
            fee_source_ref varchar(255),
            fee_calculated_at timestamptz,
            calculation_version varchar(64),

            affected_units integer not null default 0,
            affected_sales_start_date date,
            affected_sales_end_date date,
            affected_units_source varchar(64),
            estimated_recover_amount numeric(14,2) not null default 0,
            estimate_formula varchar(128),
            estimate_calculated_at timestamptz,

            claim_amount numeric(14,2),
            recovered_amount numeric(14,2) not null default 0,
            recovered_at timestamptz,

            status varchar(32) not null,
            priority varchar(16) not null default 'medium',
            severity varchar(16) not null default 'medium',
            status_changed_at timestamptz,
            status_changed_by varchar(128),
            first_alert_at timestamptz,
            case_opened_at timestamptz,
            done_at timestamptz,
            archived_at timestamptz,
            last_reopened_at timestamptz,
            reopen_count integer not null default 0,

            case_nos text,
            case_numbers_json jsonb not null default '[]'::jsonb,
            follow_log text,
            latest_follow_note text,
            log_updated_at timestamptz,
            next_follow_at date,
            follow_count integer not null default 0,
            last_follow_by varchar(128),
            last_follow_at timestamptz,
            walmart_response_summary text,
            last_rejection_reason text,
            evidence_summary text,

            archive_requested_by varchar(128),
            archive_requested_at timestamptz,
            archive_reason_type varchar(64),
            archive_reason text,
            archive_evidence text,
            archive_review_status varchar(32) not null default 'none',
            archive_reviewed_by varchar(128),
            archive_reviewed_at timestamptz,
            archive_review_note text,

            reason text,
            remark text,
            internal_note text,

            updated_by varchar(128),
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            is_deleted boolean not null default false,

            constraint ux_wfs_case_identity unique (source_account_ref, store_id, item_id, msku),
            constraint ck_wfs_case_source_kind_allowed check (
              source_kind in ('legacy_mirror','manual','future_lingxing_profit_order')
            ),
            constraint ck_wfs_case_status_allowed check (
              status in ('pending_confirm','following','archive_pending','archived','recovered')
            ),
            constraint ck_wfs_case_priority_allowed check (priority in ('high','medium','low')),
            constraint ck_wfs_case_severity_allowed check (severity in ('high','medium','low')),
            constraint ck_wfs_case_archive_review_allowed check (
              archive_review_status in ('none','pending','approved','rejected')
            ),
            constraint ck_wfs_case_manual_unit_fee_nonnegative check (manual_unit_fee >= 0),
            constraint ck_wfs_case_actual_unit_fee_nonnegative check (actual_unit_fee >= 0),
            constraint ck_wfs_case_unit_fee_diff_nonnegative check (unit_fee_diff >= 0),
            constraint ck_wfs_case_affected_units_nonnegative check (affected_units >= 0),
            constraint ck_wfs_case_estimated_recover_nonnegative check (estimated_recover_amount >= 0),
            constraint ck_wfs_case_recovered_nonnegative check (recovered_amount >= 0),
            constraint ck_wfs_case_identity_not_blank check (
              trim(source_account_ref) <> ''
              and trim(store_id) <> ''
              and trim(item_id) <> ''
              and trim(msku) <> ''
            )
        )
        """
    )

    _execute(
        """
        create index if not exists ix_wfs_case_status
          on public.ops_wfs_fee_anomaly_cases (source_account_ref, status, next_follow_at)
        """
    )
    _execute(
        """
        create index if not exists ix_wfs_case_owner
          on public.ops_wfs_fee_anomaly_cases (source_account_ref, owner_ref, status)
        """
    )
    _execute(
        """
        create index if not exists ix_wfs_case_archive_review
          on public.ops_wfs_fee_anomaly_cases
          (source_account_ref, archive_review_status, archive_requested_at)
        """
    )
    _execute(
        """
        create index if not exists ix_wfs_case_legacy
          on public.ops_wfs_fee_anomaly_cases (legacy_case_id)
        """
    )
    _execute(
        """
        create index if not exists ix_wfs_case_updated
          on public.ops_wfs_fee_anomaly_cases (updated_at desc)
        """
    )


def downgrade() -> None:
    _execute("drop table if exists public.ops_wfs_fee_anomaly_cases")
    _execute(
        """
        do $$
        begin
          if to_regclass('public.ops_wfs_fee_anomaly_cases_legacy_shape_backup') is not null then
            alter table public.ops_wfs_fee_anomaly_cases_legacy_shape_backup
              rename to ops_wfs_fee_anomaly_cases;
          end if;
        end $$;
        """
    )
