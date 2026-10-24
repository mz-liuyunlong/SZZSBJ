"""Tenant-scoped, read-only keyword run queries; no commits or mutations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AiKwAnalysisRun, AiKwRunKeyword, DimKwTerm


class KeywordPlanningRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_run(self, *, run_id: UUID, source_account_ref: str) -> AiKwAnalysisRun | None:
        return self.session.scalar(
            select(AiKwAnalysisRun).where(
                AiKwAnalysisRun.id == run_id,
                AiKwAnalysisRun.source_account_ref == source_account_ref,
            )
        )

    def list_runs(
        self, *, product_id: UUID, source_account_ref: str, limit: int, offset: int
    ) -> list[AiKwAnalysisRun]:
        return list(
            self.session.scalars(
                select(AiKwAnalysisRun)
                .where(
                    AiKwAnalysisRun.product_id == product_id,
                    AiKwAnalysisRun.source_account_ref == source_account_ref,
                )
                .order_by(AiKwAnalysisRun.created_at.desc(), AiKwAnalysisRun.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )

    def count_runs(self, *, product_id: UUID, source_account_ref: str) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(AiKwAnalysisRun)
                .where(
                    AiKwAnalysisRun.product_id == product_id,
                    AiKwAnalysisRun.source_account_ref == source_account_ref,
                )
            )
            or 0
        )

    def count_keywords(self, *, run_id: UUID, source_account_ref: str) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(AiKwRunKeyword)
                .where(
                    AiKwRunKeyword.run_id == run_id,
                    AiKwRunKeyword.source_account_ref == source_account_ref,
                )
            )
            or 0
        )

    def list_keywords(self, *, run_id: UUID, source_account_ref: str, limit: int, offset: int):
        return list(
            self.session.execute(
                select(AiKwRunKeyword, DimKwTerm.canonical_keyword)
                .join(DimKwTerm, DimKwTerm.id == AiKwRunKeyword.term_id)
                .where(
                    AiKwRunKeyword.run_id == run_id,
                    AiKwRunKeyword.source_account_ref == source_account_ref,
                )
                .order_by(
                    AiKwRunKeyword.rank_index.asc().nulls_last(),
                    AiKwRunKeyword.term_id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
        )
