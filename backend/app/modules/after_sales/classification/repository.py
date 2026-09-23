from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import text

from app.modules.after_sales.classification.schemas import (
    ClassificationRule,
    ReasonDefinition,
    ResponsibilityDefinition,
)


class SqlExecutor(Protocol):
    def execute(self, statement: Any, parameters: dict[str, object] | None = None) -> Any: ...


class AfterSalesClassificationRepository:
    """Read classification dictionaries/rules from PostgreSQL.

    The importer and backfill scripts pass a SQLAlchemy Connection. Runtime services may
    pass a Session. Both satisfy the small execute() contract used here.
    """

    def __init__(self, executor: SqlExecutor) -> None:
        self.executor = executor

    def load_reason_definitions(self) -> dict[str, ReasonDefinition]:
        rows = (
            self.executor.execute(
                text(
                    """
                    select
                        reason_code,
                        reason_name_cn,
                        category_code,
                        category_name_cn,
                        tag_color
                    from after_sales_reason_dict
                    where enabled = true
                    order by sort_order, reason_code
                    """
                )
            )
            .mappings()
            .all()
        )
        return {
            str(row["reason_code"]): ReasonDefinition(
                reason_code=str(row["reason_code"]),
                reason_name_cn=str(row["reason_name_cn"]),
                category_code=str(row["category_code"]),
                category_name_cn=str(row["category_name_cn"]),
                tag_color=str(row["tag_color"]),
            )
            for row in rows
        }

    def load_responsibility_definitions(self) -> dict[str, ResponsibilityDefinition]:
        rows = (
            self.executor.execute(
                text(
                    """
                    select code, name_cn, tag_color
                    from after_sales_responsibility_dict
                    where enabled = true
                    order by sort_order, code
                    """
                )
            )
            .mappings()
            .all()
        )
        return {
            str(row["code"]): ResponsibilityDefinition(
                code=str(row["code"]),
                name_cn=str(row["name_cn"]),
                tag_color=str(row["tag_color"]),
            )
            for row in rows
        }

    def load_rules(self, platform_code: str = "walmart") -> list[ClassificationRule]:
        rows = (
            self.executor.execute(
                text(
                    """
                    select
                        id,
                        raw_reason_code,
                        match_type,
                        match_value,
                        keywords_all,
                        keywords_any,
                        keywords_exclude,
                        normalized_reason_code,
                        responsibility_code,
                        priority,
                        confidence,
                        rule_version
                    from after_sales_reason_rules
                    where platform_code = :platform_code
                      and enabled = true
                    order by priority desc, id
                    """
                ),
                {"platform_code": platform_code},
            )
            .mappings()
            .all()
        )
        return [
            ClassificationRule(
                id=str(row["id"]),
                raw_reason_code=(str(row["raw_reason_code"]) if row["raw_reason_code"] else None),
                match_type=str(row["match_type"]),  # type: ignore[arg-type]
                match_value=str(row["match_value"]) if row["match_value"] else None,
                keywords_all=tuple(str(value) for value in (row["keywords_all"] or [])),
                keywords_any=tuple(str(value) for value in (row["keywords_any"] or [])),
                keywords_exclude=tuple(str(value) for value in (row["keywords_exclude"] or [])),
                normalized_reason_code=str(row["normalized_reason_code"]),
                responsibility_code=str(row["responsibility_code"]),
                priority=int(row["priority"]),
                confidence=str(row["confidence"]),  # type: ignore[arg-type]
                rule_version=str(row["rule_version"]),
            )
            for row in rows
        ]
