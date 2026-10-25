"""Install a versioned, internal-only keyword analysis baseline.

Revision ID: 20261025_0058_keyword_internal_default
Revises: 20261024_0057_keyword_rule_decisions
"""

import hashlib
import json
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision: str = "20261025_0058_keyword_internal_default"
down_revision: str | Sequence[str] | None = "20261024_0057_keyword_rule_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RULE_SET_ID = UUID("846c10c2-090f-4ef0-8be8-5741981184ba")
RULE_VERSION_ID = UUID("952b95a8-daca-4831-867c-a73d0ed488b4")
RULE_KEY = "keyword_v11_internal_default"
CONFIG = {
    "limits": {
        "max_p0": 5,
        "max_p1": 10,
        "max_p2": 30,
        "max_exact": 20,
        "max_broad_roots": 5,
        "max_broad_long_tails": 15,
    },
    "confirmed_brands": {},
    "suspected_brands": {},
    "business_approvals": {f"D{i:02d}": "pending" for i in range(1, 9)},
    "automatic_classification_approved": False,
    "official_bulk_template_approved": False,
    "purpose": "internal_analysis_and_manual_review_only",
    "editor_config": {
        "weights": {"match": 30, "intent": 20, "coverage": 20, "root": 15, "market": 15},
        "thresholds": {"p0": 85, "p1": 75, "p2": 60},
        "limits": {"p0": 5, "p1": 10, "p2": 30, "exact": 20, "broad": 20, "roots": 5},
        "asin": {"min": 3, "recommend": 3, "max": 5, "titleWeight": 2, "featuresWeight": 1},
        "riskWords": "",
        "bid": {"exact": 0, "broad": 0, "auto": 0, "dailyBudget": 0, "startDate": ""},
        "naming": {"manual": "", "auto": ""},
        "listing": {"features": 5, "titleMax": 180, "description": True},
        "export": {"sheetNames": "", "columnNames": ""},
    },
}
CONFIG_JSON = json.dumps(CONFIG, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
CONFIG_SHA256 = hashlib.sha256(CONFIG_JSON.encode("utf-8")).hexdigest()


def upgrade() -> None:
    connection = op.get_bind()
    # Existing databases passed the IAM catalogue migration before this page existed.
    # Register permissions without granting them to any role.
    connection.execute(
        sa.text("""
            INSERT INTO app_permissions
                (permission_key, name, group_key, description, permission_type,
                 module_key, page_key, action_key, field_key, risk_level,
                 sort_order, is_active, created_at, updated_at)
            VALUES
                ('page:ai-center:keyword-launch:view', '关键词投放', 'AI中心',
                 '允许查看关键词来源、规则和分析', 'page', 'ai_center',
                 'ai_center_keyword_launch', NULL, NULL, 'normal', 110080,
                 true, now(), now()),
                ('action:ai-center:keyword-launch:manage', '维护关键词来源与分析',
                 'AI中心', '允许保存关键词来源、上传和内部分析', 'action',
                 'ai_center', 'ai_center_keyword_launch', 'manage', NULL,
                 'normal', 10, true, now(), now())
            ON CONFLICT (permission_key) DO NOTHING
        """)
    )
    connection.execute(
        sa.text("""
            INSERT INTO ai_kw_rule_set
                (id, rule_key, scope_key, rule_type, display_name, is_enabled, created_by)
            VALUES (:id, :key, 'global', 'scoring',
                    'Walmart 关键词内部分析默认规则', true, 'system-bootstrap')
            ON CONFLICT (rule_key, scope_key) DO NOTHING
        """),
        {"id": RULE_SET_ID, "key": RULE_KEY},
    )
    rule_set = connection.execute(
        sa.text("""
            SELECT id, rule_type, is_enabled FROM ai_kw_rule_set
            WHERE rule_key=:key AND scope_key='global'
        """),
        {"key": RULE_KEY},
    ).one()
    if rule_set.id != RULE_SET_ID or rule_set.rule_type != "scoring" or not rule_set.is_enabled:
        raise RuntimeError("KEYWORD_DEFAULT_RULE_SET_CONFLICT")
    connection.execute(
        sa.text("""
            INSERT INTO ai_kw_rule_version
                (id, rule_set_id, version_number, status, config_json, config_sha256,
                 schema_version, engine_version, published_by, published_at)
            VALUES (:id, :set_id, 1, 'published', CAST(:config AS jsonb), :digest,
                    'v1.1-system-default-internal', 'v1_1_versioned_scoring_20261025',
                    'system-bootstrap', now())
            ON CONFLICT (rule_set_id, version_number) DO NOTHING
        """),
        {
            "id": RULE_VERSION_ID,
            "set_id": RULE_SET_ID,
            "config": CONFIG_JSON,
            "digest": CONFIG_SHA256,
        },
    )
    version = connection.execute(
        sa.text("""
            SELECT id, status, config_sha256 FROM ai_kw_rule_version
            WHERE rule_set_id=:set_id AND version_number=1
        """),
        {"set_id": RULE_SET_ID},
    ).one()
    if (
        version.id != RULE_VERSION_ID
        or version.status != "published"
        or version.config_sha256 != CONFIG_SHA256
    ):
        raise RuntimeError("KEYWORD_DEFAULT_RULE_VERSION_CONFLICT")


def downgrade() -> None:
    raise RuntimeError("KEYWORD_DEFAULT_RULE_IS_IMMUTABLE_AND_MAY_BE_REFERENCED_BY_RUNS")
