"""Seed one traceable Listing evaluation rule without changing historical runs."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "20261104_0073_listing_grade_default_rule"
down_revision: str | Sequence[str] | None = "20261102_0072_list_skill_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen V1 defaults. Do not import mutable application settings into migrations.
DEFAULT_RULES = {
    "execution_time": "22:30",
    "short_days": 7,
    "medium_days": 14,
    "short_weight_percent": 60,
    "medium_weight_percent": 40,
    "short_min_valid_days": 4,
    "medium_min_valid_days": 8,
    "c_min_percent": "5",
    "b_min_percent": "10",
    "a_above_percent": "15",
    "included_stages": ["打品期", "启动期", "上升期", "稳定期", "下滑期", "修复期"],
    "lifecycle": {
        "min_week_valid_days": 4,
        "growth_min_valid_days_30": 14,
        "decline_min_valid_days_30": 21,
        "stable_min_valid_days_30": 21,
        "growth_threshold_pct": {
            "lt2": 50,
            "from2to5": 40,
            "from5to10": 30,
            "from10to20": 25,
            "gte20": 20,
        },
        "decline_threshold_pct": {
            "lt2": 50,
            "from2to5": 40,
            "from5to10": 30,
            "from10to20": 25,
            "gte20": 20,
        },
        "stable_tolerance_pct": {
            "lt2": 60,
            "from2to5": 45,
            "from5to10": 35,
            "from10to20": 30,
            "gte20": 25,
        },
    },
    "inventory_repair": {
        "low_stock_max_units": 5,
        "stockout_consecutive_days": 7,
        "long_stockout_days": 25,
        "stockout_repair_valid_days": 15,
        "strike_price_abnormal_days": 25,
        "buybox_abnormal_days": 25,
        "abnormal_recovery_days": 7,
    },
    "follow_up": {
        "reminder_time": None,
        "deadline_time": None,
        "overdue_notice": False,
    },
}


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO biz_listing_grade_rule_versions
              (version, config_json, effective_from, created_at, created_by, change_reason)
            SELECT 1, CAST(:config AS jsonb), :effective_from, :created_at,
                   'system', 'System default Listing rule V1'
            WHERE NOT EXISTS (SELECT 1 FROM biz_listing_grade_rule_versions)
            ON CONFLICT (version) DO NOTHING
            """
        ),
        {
            "config": json.dumps(DEFAULT_RULES, ensure_ascii=False, sort_keys=True),
            "effective_from": datetime(1970, 1, 1, tzinfo=UTC),
            "created_at": datetime.now(UTC),
        },
    )


def downgrade() -> None:
    raise RuntimeError("LISTING_RULE_HISTORY_REQUIRES_VERIFIED_BACKUP_RESTORE")
