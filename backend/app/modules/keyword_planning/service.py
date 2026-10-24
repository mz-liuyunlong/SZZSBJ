"""Authenticated account-scoped read projections of persisted analysis runs."""

from __future__ import annotations

from uuid import UUID

from app.core.api import ApiError, ErrorCode

from .repository import KeywordPlanningRepository
from .schemas import KeywordListRead, KeywordRead, RunListRead, RunRead


class KeywordPlanningService:
    def __init__(self, repo: KeywordPlanningRepository, allowed_accounts: frozenset[str]):
        self.repo = repo
        self.allowed_accounts = allowed_accounts

    def _guard(self, account: str) -> None:
        if account not in self.allowed_accounts or not account.strip():
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)

    def _run(self, run_id: UUID, account: str):
        self._guard(account)
        run = self.repo.get_run(run_id=run_id, source_account_ref=account)
        if run is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return run

    def _read_run(self, run) -> RunRead:
        return RunRead(
            run_id=run.id,
            product_id=run.product_id,
            source_account_ref=run.source_account_ref,
            item_id=run.item_id,
            status=run.status,
            rule_version_id=run.rule_version_id,
            created_at=run.created_at,
            finished_at=run.finished_at,
            keyword_count=self.repo.count_keywords(
                run_id=run.id,
                source_account_ref=run.source_account_ref,
            ),
        )

    def get_run(self, *, run_id: UUID, account: str) -> RunRead:
        return self._read_run(self._run(run_id, account))

    def list_runs(self, *, product_id: UUID, account: str, limit: int, offset: int) -> RunListRead:
        self._guard(account)
        total = self.repo.count_runs(product_id=product_id, source_account_ref=account)
        rows = self.repo.list_runs(
            product_id=product_id,
            source_account_ref=account,
            limit=limit,
            offset=offset,
        )
        return RunListRead(
            items=[self._read_run(run) for run in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def list_keywords(
        self, *, run_id: UUID, account: str, limit: int, offset: int
    ) -> KeywordListRead:
        self._run(run_id, account)
        total = self.repo.count_keywords(run_id=run_id, source_account_ref=account)
        rows = self.repo.list_keywords(
            run_id=run_id,
            source_account_ref=account,
            limit=limit,
            offset=offset,
        )
        result = [
            KeywordRead(
                term_id=row.term_id,
                keyword=term,
                primary_type=row.keyword_primary_type,
                page_coverage=row.page_coverage,
                core_root=row.core_root,
                score=row.score,
                base_grade=row.base_grade,
                allocation_grade=row.allocation_grade,
                exact_selected=row.exact_selected,
                broad_selected=row.broad_selected,
                broad_role=row.broad_role,
                suggested_optimization_bid=row.suggested_optimization_bid,
                decision_status=row.decision_status,
                risk_reasons=row.risk_reasons_json,
                exact_reason=row.exact_reason,
                broad_reason=row.broad_reason,
                quality_note=row.quality_note,
                rank_index=row.rank_index,
            )
            for row, term in rows
        ]
        return KeywordListRead(
            run_id=run_id,
            items=result,
            total=total,
            limit=limit,
            offset=offset,
            official_export_authorized=False,
        )
