"""Read-only new-product board aggregates from scoped business tables.

No simulated successes, sales, grades or financial values are returned.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

GROUP_KEYS = ("category", "developer", "operator", "purchase_status", "tracking_status")


def read_new_product_dashboard(session: Session, *, account: str) -> dict[str, Any]:
    rows = (
        session.execute(
            text(
                """
                WITH records AS (
                    SELECT
                        COALESCE(NULLIF(p.category, ''), '未分类') AS category,
                        COALESCE(NULLIF(detail.product_developer_name, ''), '未分配')
                            AS developer,
                        COALESCE(NULLIF(detail.owner_name, ''), '未分配') AS operator,
                        COALESCE(workflow.status, 'pending_market') AS purchase_status,
                        CASE
                            WHEN workflow.status IS DISTINCT FROM 'approved_draft'
                                THEN 'not_in_pool'
                            WHEN workflow.arrival_date IS NULL
                                 OR workflow.sellable_date IS NULL
                                THEN 'awaiting_sellable'
                            WHEN workflow.review_result = 'optimize'
                                THEN 'optimize'
                            WHEN workflow.review_due_at IS NOT NULL
                                 AND workflow.review_due_at <=
                                     timezone('America/Los_Angeles', now())::date
                                THEN 'due_review'
                            ELSE 'observing'
                        END AS tracking_status
                    FROM dwd_lingxing_sku_identity_index AS identity
                    LEFT JOIN products AS p
                        ON p.id = identity.product_id AND p.deleted_at IS NULL
                    LEFT JOIN dwd_lingxing_sku_product_info_current AS detail
                        ON detail.identity_id = identity.id
                       AND detail.source_account_ref = identity.source_account_ref
                    LEFT JOIN product_new_workflows AS workflow
                        ON workflow.sku_identity_id = identity.id
                       AND workflow.source_account_ref = identity.source_account_ref
                    WHERE identity.source_account_ref = :account
                      AND identity.is_active IS TRUE
                )
                SELECT CASE
                    WHEN GROUPING(category) = 0 THEN 'category'
                    WHEN GROUPING(developer) = 0 THEN 'developer'
                    WHEN GROUPING(operator) = 0 THEN 'operator'
                    WHEN GROUPING(purchase_status) = 0 THEN 'purchase_status'
                    ELSE 'tracking_status'
                END AS group_type,
                COALESCE(category, developer, operator, purchase_status, tracking_status)
                    AS group_name,
                count(*) AS product_count
                FROM records
                GROUP BY GROUPING SETS (
                    (category), (developer), (operator),
                    (purchase_status), (tracking_status)
                )
                """
            ),
            {"account": account},
        )
        .mappings()
        .all()
    )
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in GROUP_KEYS}
    for row in rows:
        kind = row["group_type"]
        if kind not in groups:
            continue
        groups[kind].append({"name": row["group_name"], "count": int(row["product_count"])})
    for entries in groups.values():
        entries.sort(key=lambda item: (-item["count"], item["name"]))
    total = sum(entry["count"] for entry in groups["purchase_status"])
    return {
        "account": account,
        "total": total,
        "groups": groups,
        "formal_grade_distribution": None,
        "formal_launch_success_rate": None,
        "formal_rules_status": "awaiting_owner_approved_scoring_contract",
    }
