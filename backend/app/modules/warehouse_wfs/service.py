from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.warehouse_wfs.legacy_identity import (
    LEGACY_IDENTITY_CTE,
    LEGACY_IDENTITY_PREFLIGHT_SQL,
)
from app.modules.warehouse_wfs.schemas import (
    WfsFeeAlertListData,
    WfsFeeAlertQuery,
    WfsFeeAlertRead,
    WfsFeeArchiveRequestWrite,
    WfsFeeArchiveReviewWrite,
    WfsFeeCaseFollowWrite,
    WfsFeeCaseListData,
    WfsFeeCaseQuery,
    WfsFeeCaseRead,
    WfsFeeCaseWrite,
    WfsFeeLegacyCompareResult,
    WfsFeeLegacySyncResult,
    WfsFeeRecoveredWrite,
)

LEGACY_STATUS_TO_CASE_STATUS = {
    "waiting": "pending_confirm",
    "following": "following",
    "approving": "archive_pending",
    "closed": "archived",
    "done": "recovered",
}

CASE_STATUS_TO_LABEL = {
    "pending_confirm": "未开Case",
    "following": "跟进中",
    "archive_pending": "驳回",
    "archived": "已关闭",
    "recovered": "已追回",
}

CASE_LABEL_TO_STATUS = {
    "未开Case": "pending_confirm",
    "已开Case": "following",
    "跟进中": "following",
    "驳回": "archive_pending",
    "已关闭": "archived",
    "已追回": "recovered",
}

PRIORITY_TO_LABEL = {"high": "高", "medium": "中", "low": "低"}
PRIORITY_LABEL_TO_VALUE = {"高": "high", "中": "medium", "低": "low"}


def utc_now() -> datetime:
    return datetime.now(UTC)


def map_legacy_status(status: str | None) -> str:
    return LEGACY_STATUS_TO_CASE_STATUS.get(str(status or "").strip(), "pending_confirm")


def map_priority_by_amount(amount: Decimal | None) -> str:
    value = amount or Decimal("0")
    if value >= Decimal("500"):
        return "high"
    if value >= Decimal("100"):
        return "medium"
    return "low"


def stable_legacy_uuid_expr(alias: str = "l") -> str:
    # Keep SQL-side UUID deterministic without relying on pgcrypto/gen_random_uuid.
    return (
        "(substr(md5(" + alias + ".id::text),1,8)||'-'||"
        "substr(md5(" + alias + ".id::text),9,4)||'-'||"
        "substr(md5(" + alias + ".id::text),13,4)||'-'||"
        "substr(md5(" + alias + ".id::text),17,4)||'-'||"
        "substr(md5(" + alias + ".id::text),21,12))::uuid"
    )


class WfsFeeAlertService:
    """Manage formal WFS anomaly cases.

    This service intentionally does not update Daily Sales, Order Profit, or
    fact_walmart_wfs_fee_actual. Current production evidence shows WFS fee RAW is
    not in ODS; legacy_mirror.event_wfs_fee_case is the transitional source of
    truth for case workflow data.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_cases(
        self,
        query: WfsFeeCaseQuery,
        account_refs: frozenset[str],
    ) -> tuple[WfsFeeCaseListData, int]:
        rows, total = self._fetch_case_rows(query, account_refs)
        return WfsFeeCaseListData(items=[WfsFeeCaseRead(**dict(row)) for row in rows]), total

    def list_alerts(
        self,
        query: WfsFeeAlertQuery,
        account_refs: frozenset[str],
    ) -> tuple[WfsFeeAlertListData, int]:
        normalized = WfsFeeCaseQuery(
            start_date=query.start_date,
            end_date=query.end_date,
            store_id=query.store_id,
            owner_ref=query.owner_ref,
            status=CASE_LABEL_TO_STATUS.get(str(query.status), query.status)
            if query.status
            else None,
            keyword=query.keyword,
            page=query.page,
            page_size=query.page_size,
        )
        rows, total = self._fetch_case_rows(normalized, account_refs)
        items = [self._to_alert_compat(dict(row)) for row in rows]
        return WfsFeeAlertListData(items=items), total

    def get_case(self, case_id: UUID, account_refs: frozenset[str]) -> WfsFeeCaseRead:
        row = (
            self.session.execute(
                text(
                    self._case_select_sql()
                    + (
                        " where id=:case_id and source_account_ref=any(:accounts)"
                        " and is_deleted=false"
                    )
                ),
                {"case_id": str(case_id), "accounts": list(account_refs)},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return WfsFeeCaseRead(**dict(row))

    def save_follow(
        self,
        case_id: UUID,
        payload: WfsFeeCaseFollowWrite,
        account_refs: frozenset[str],
        actor_ref: str,
    ) -> None:
        self._assert_case_visible(case_id, account_refs)
        now = utc_now()
        result = self.session.execute(
            text(
                """
                update ops_wfs_fee_anomaly_cases set
                  status = 'following',
                  archive_review_status = case
                    when archive_review_status = 'pending' then 'rejected'
                    else archive_review_status
                  end,
                  case_nos = nullif(:case_nos, ''),
                  latest_follow_note = :latest_follow_note,
                  follow_log = concat_ws(E'\n', nullif(follow_log, ''), :latest_follow_note),
                  log_updated_at = :now,
                  next_follow_at = :next_follow_at,
                  follow_count = follow_count + 1,
                  last_follow_by = :actor,
                  last_follow_at = :now,
                  walmart_response_summary = nullif(:walmart_response_summary, ''),
                  evidence_summary = nullif(:evidence_summary, ''),
                  status_changed_at = :now,
                  status_changed_by = :actor,
                  updated_by = :actor,
                  updated_at = :now
                where id = :case_id
                  and status in ('pending_confirm','following')
                """
            ),
            {
                "case_id": str(case_id),
                "case_nos": payload.case_nos,
                "latest_follow_note": payload.latest_follow_note,
                "next_follow_at": payload.next_follow_at,
                "walmart_response_summary": payload.walmart_response_summary,
                "evidence_summary": payload.evidence_summary,
                "actor": actor_ref,
                "now": now,
            },
        )
        if result.rowcount != 1:
            self.session.rollback()
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
        self.session.commit()

    def update_case(
        self,
        case_id: UUID,
        payload: WfsFeeCaseWrite,
        account_refs: frozenset[str],
        actor_ref: str,
    ) -> None:
        """Compatibility action for the current frontend follow modal."""

        self._assert_case_visible(case_id, account_refs)
        status = CASE_LABEL_TO_STATUS[payload.status]
        if status not in ("pending_confirm", "following"):
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=422)
        priority = PRIORITY_LABEL_TO_VALUE[payload.priority]
        latest_note = payload.latest_follow or payload.reason or payload.status
        now = utc_now()
        result = self.session.execute(
            text(
                """
                update ops_wfs_fee_anomaly_cases set
                  status = :status,
                  priority = :priority,
                  case_nos = nullif(:case_no, ''),
                  reason = nullif(:reason, ''),
                  claim_amount = :claim_amount,
                  case_opened_at = :case_opened_at,
                  next_follow_at = :next_follow_at,
                  latest_follow_note = nullif(:latest_follow, ''),
                  follow_log = case when nullif(:latest_follow, '') is null then follow_log
                    else concat_ws(E'\n', nullif(follow_log, ''), :latest_follow) end,
                  log_updated_at = case when nullif(:latest_follow, '') is null then log_updated_at
                    else :now end,
                  status_changed_at = :now,
                  status_changed_by = :actor,
                  updated_by = :actor,
                  updated_at = :now
                where id = :case_id
                  and status in ('pending_confirm','following')
                """
            ),
            {
                "case_id": str(case_id),
                "status": status,
                "priority": priority,
                "case_no": payload.case_no,
                "reason": payload.reason,
                "claim_amount": payload.claim_amount,
                "case_opened_at": payload.case_opened_at,
                "next_follow_at": payload.next_follow_at,
                "latest_follow": latest_note,
                "actor": actor_ref,
                "now": now,
            },
        )
        if result.rowcount != 1:
            self.session.rollback()
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
        self.session.commit()

    def request_archive(
        self,
        case_id: UUID,
        payload: WfsFeeArchiveRequestWrite,
        account_refs: frozenset[str],
        actor_ref: str,
    ) -> None:
        self._assert_case_visible(case_id, account_refs)
        now = utc_now()
        result = self.session.execute(
            text(
                """
                update ops_wfs_fee_anomaly_cases set
                  status = 'archive_pending',
                  archive_review_status = 'pending',
                  archive_requested_by = :actor,
                  archive_requested_at = :now,
                  archive_reason_type = :archive_reason_type,
                  archive_reason = :archive_reason,
                  archive_evidence = nullif(:archive_evidence, ''),
                  status_changed_at = :now,
                  status_changed_by = :actor,
                  updated_by = :actor,
                  updated_at = :now
                where id = :case_id
                  and status in ('pending_confirm','following','archive_pending')
                """
            ),
            {
                "case_id": str(case_id),
                "archive_reason_type": payload.archive_reason_type,
                "archive_reason": payload.archive_reason,
                "archive_evidence": payload.archive_evidence,
                "actor": actor_ref,
                "now": now,
            },
        )
        if result.rowcount != 1:
            self.session.rollback()
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
        self.session.commit()

    def review_archive(
        self,
        case_id: UUID,
        payload: WfsFeeArchiveReviewWrite,
        account_refs: frozenset[str],
        actor_ref: str,
    ) -> None:
        self._assert_case_visible(case_id, account_refs)
        now = utc_now()
        if payload.decision == "approved":
            values = {
                "status": "archived",
                "review_status": "approved",
                "archived_at": now,
                "last_reopened_at": None,
            }
        else:
            values = {
                "status": "following",
                "review_status": "rejected",
                "archived_at": None,
                "last_reopened_at": now,
            }
        result = self.session.execute(
            text(
                """
                update ops_wfs_fee_anomaly_cases set
                  status = :status,
                  archive_review_status = :review_status,
                  archive_reviewed_by = :actor,
                  archive_reviewed_at = :now,
                  archive_review_note = nullif(:note, ''),
                  archived_at = coalesce(:archived_at, archived_at),
                  last_reopened_at = coalesce(:last_reopened_at, last_reopened_at),
                  reopen_count = case when :review_status='rejected'
                    then reopen_count + 1 else reopen_count end,
                  status_changed_at = :now,
                  status_changed_by = :actor,
                  updated_by = :actor,
                  updated_at = :now
                where id = :case_id
                  and status = 'archive_pending'
                  and archive_review_status = 'pending'
                  and archive_requested_by is distinct from :actor
                """
            ),
            {
                "case_id": str(case_id),
                "actor": actor_ref,
                "now": now,
                "note": payload.archive_review_note,
                **values,
            },
        )
        if result.rowcount != 1:
            self.session.rollback()
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
        self.session.commit()

    def mark_recovered(
        self,
        case_id: UUID,
        payload: WfsFeeRecoveredWrite,
        account_refs: frozenset[str],
        actor_ref: str,
    ) -> None:
        self._assert_case_visible(case_id, account_refs)
        now = utc_now()
        self.session.execute(
            text(
                """
                update ops_wfs_fee_anomaly_cases set
                  status = 'recovered',
                  claim_amount = coalesce(:claim_amount, claim_amount),
                  recovered_amount = :recovered_amount,
                  recovered_at = :now,
                  done_at = :now,
                  latest_follow_note =
                    coalesce(nullif(:latest_follow_note, ''), latest_follow_note),
                  follow_log = case when nullif(:latest_follow_note, '') is null then follow_log
                    else concat_ws(E'\n', nullif(follow_log, ''), :latest_follow_note) end,
                  log_updated_at = case when nullif(:latest_follow_note, '') is null
                    then log_updated_at
                    else :now end,
                  status_changed_at = :now,
                  status_changed_by = :actor,
                  updated_by = :actor,
                  updated_at = :now
                where id = :case_id
                """
            ),
            {
                "case_id": str(case_id),
                "claim_amount": payload.claim_amount,
                "recovered_amount": payload.recovered_amount,
                "latest_follow_note": payload.latest_follow_note,
                "actor": actor_ref,
                "now": now,
            },
        )
        self.session.commit()

    def sync_legacy_cases(self, *, execute: bool) -> WfsFeeLegacySyncResult:
        summary = self._legacy_sync_summary()
        if not execute:
            return summary
        if (
            summary.unmatched_identities
            or summary.ambiguous_identities
            or summary.duplicate_identities
            or summary.invalid_values
            or summary.case_ref_conflicts
        ):
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
        result = self.session.execute(text(self._legacy_upsert_sql()))
        self.session.commit()
        return WfsFeeLegacySyncResult(
            **summary.model_dump(exclude={"execute", "inserted_or_updated"}),
            execute=True,
            inserted_or_updated=int(result.rowcount or 0),
        )

    def compare_legacy_cases(self) -> WfsFeeLegacyCompareResult:
        row = (
            self.session.execute(
                text(
                    """
                    with legacy as (
                      select
                        id legacy_case_id,
                        manual_fee,
                        actual_fee,
                        total_units affected_units,
                        est_recover estimated_recover_amount
                      from legacy_mirror.event_wfs_fee_case
                      where platform = 'walmart'
                    ), formal as (
                      select
                        legacy_case_id,
                        manual_unit_fee,
                        actual_unit_fee,
                        affected_units,
                        estimated_recover_amount
                      from ops_wfs_fee_anomaly_cases
                      where source_kind = 'legacy_mirror' and is_deleted = false
                    ), paired as (
                      select
                        l.legacy_case_id l_id,
                        f.legacy_case_id f_id,
                        l.manual_fee,
                        f.manual_unit_fee,
                        l.actual_fee,
                        f.actual_unit_fee,
                        l.affected_units l_units,
                        f.affected_units f_units,
                        l.estimated_recover_amount l_est,
                        f.estimated_recover_amount f_est
                      from legacy l
                      full join formal f on f.legacy_case_id = l.legacy_case_id
                    )
                    select
                      count(*) filter (where l_id is not null and f_id is not null) compared,
                      count(*) filter (
                        where l_id is not null and f_id is not null
                          and abs(actual_fee - actual_unit_fee) <= 0.01
                          and abs(manual_fee - manual_unit_fee) <= 0.01
                          and l_units = f_units
                          and abs(l_est - f_est) <= 1
                      ) matched,
                      count(*) filter (where l_id is not null and f_id is null) only_in_legacy,
                      count(*) filter (where l_id is null and f_id is not null) only_in_formal,
                      count(*) filter (
                        where l_id is not null and f_id is not null
                          and abs(actual_fee - actual_unit_fee) > 0.01
                      ) actual_fee_diff,
                      count(*) filter (
                        where l_id is not null and f_id is not null
                          and abs(manual_fee - manual_unit_fee) > 0.01
                      ) manual_fee_diff,
                      count(*) filter (
                        where l_id is not null and f_id is not null and l_units <> f_units
                      ) affected_units_diff,
                      count(*) filter (
                        where l_id is not null and f_id is not null and abs(l_est - f_est) > 1
                      ) estimated_recover_diff
                    from paired
                    """
                )
            )
            .mappings()
            .one()
        )
        return WfsFeeLegacyCompareResult(**dict(row))

    def _fetch_case_rows(
        self,
        query: WfsFeeCaseQuery,
        account_refs: frozenset[str],
    ) -> tuple[list[dict], int]:
        where = ["source_account_ref = any(:accounts)", "is_deleted = false"]
        params: dict[str, object] = {"accounts": list(account_refs)}
        if query.start_date is not None:
            where.append("coalesce(first_alert_at, created_at)::date >= :start_date")
            params["start_date"] = query.start_date
        if query.end_date is not None:
            where.append("coalesce(first_alert_at, created_at)::date <= :end_date")
            params["end_date"] = query.end_date
        if query.store_id is not None:
            where.append("store_id = :store_id")
            params["store_id"] = query.store_id
        if query.owner_ref is not None:
            where.append("owner_ref = :owner_ref")
            params["owner_ref"] = query.owner_ref
        if query.status is not None:
            where.append("status = :status")
            params["status"] = query.status
        if query.priority is not None:
            where.append("priority = :priority")
            params["priority"] = query.priority
        if query.archive_review_status is not None:
            where.append("archive_review_status = :archive_review_status")
            params["archive_review_status"] = query.archive_review_status
        if query.keyword:
            where.append(
                "(store_name_snapshot ilike :keyword or item_id ilike :keyword or "
                "msku ilike :keyword or case_nos ilike :keyword or "
                "owner_name_snapshot ilike :keyword or product_name_snapshot ilike :keyword)"
            )
            params["keyword"] = f"%{query.keyword}%"
        where_sql = " and ".join(where)
        total = int(
            self.session.execute(
                text(f"select count(*) from ops_wfs_fee_anomaly_cases where {where_sql}"),
                params,
            ).scalar_one()
        )
        params.update({"limit": query.page_size, "offset": (query.page - 1) * query.page_size})
        rows = (
            self.session.execute(
                text(
                    self._case_select_sql()
                    + f" where {where_sql} "
                    + " order by case status "
                    + " when 'archive_pending' then 1 "
                    + " when 'following' then 2 "
                    + " when 'pending_confirm' then 3 "
                    + " when 'recovered' then 4 "
                    + " else 5 end, estimated_recover_amount desc, updated_at desc "
                    + " limit :limit offset :offset"
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows], total

    def _to_alert_compat(self, row: dict) -> WfsFeeAlertRead:
        affected_units = Decimal(row["affected_units"] or 0)
        expected_total = (row["manual_unit_fee"] or Decimal("0")) * affected_units
        actual_total = (row["actual_unit_fee"] or Decimal("0")) * affected_units
        variance = row["estimated_recover_amount"] or Decimal("0")
        expected_unit = row["manual_unit_fee"]
        variance_rate = None
        if expected_total and expected_total > 0:
            variance_rate = variance / expected_total
        return WfsFeeAlertRead(
            id=row["id"],
            business_date_la=(row["first_alert_at"] or row["created_at"]).date(),
            store_id=row["store_id"],
            store_name=row["store_name_snapshot"],
            owner_ref=row["owner_ref"],
            item_id=row["item_id"],
            msku=row["msku"],
            local_sku=row["local_sku_snapshot"],
            product_name=row["product_name_snapshot"],
            order_count=affected_units,
            sales_qty=affected_units,
            cost_quantity=affected_units,
            expected_fee_amount=expected_total,
            actual_fee_amount=actual_total,
            variance_amount=variance,
            variance_rate=variance_rate,
            expected_unit_amount=expected_unit,
            actual_unit_amount=row["actual_unit_fee"],
            status=CASE_STATUS_TO_LABEL[row["status"]],
            case_no=row["case_nos"],
            reason=row["reason"] or row["archive_reason"],
            priority=PRIORITY_TO_LABEL[row["priority"]],
            claim_amount=row["claim_amount"],
            recovered_amount=row["recovered_amount"],
            pending_recovery_amount=row["pending_recover_amount"],
            case_opened_at=row["case_opened_at"],
            next_follow_at=row["next_follow_at"],
            latest_follow=row["latest_follow_note"] or row["follow_log"],
        )

    def _assert_case_visible(self, case_id: UUID, account_refs: frozenset[str]) -> None:
        exists = self.session.execute(
            text(
                """
                select 1
                from ops_wfs_fee_anomaly_cases
                where id=:case_id and source_account_ref=any(:accounts) and is_deleted=false
                """
            ),
            {"case_id": str(case_id), "accounts": list(account_refs)},
        ).first()
        if exists is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

    def _legacy_sync_summary(self) -> WfsFeeLegacySyncResult:
        row = (
            self.session.execute(
                text(
                    LEGACY_IDENTITY_PREFLIGHT_SQL
                    + """,
                (select count(*) from ops_wfs_fee_anomaly_cases
                 where source_kind = 'legacy_mirror' and is_deleted = false)
                   existing_cases,
                (select count(*) from enriched e
                 left join ops_wfs_fee_anomaly_cases c
                   on c.source_account_ref=e.source_account_ref
                  and c.store_id=e.store_id and c.item_id=e.item_id
                  and c.msku=e.normalized_msku
                 where c.id is null) will_insert,
                (select count(*) from enriched e
                 join ops_wfs_fee_anomaly_cases c
                   on c.source_account_ref=e.source_account_ref
                  and c.store_id=e.store_id and c.item_id=e.item_id
                  and c.msku=e.normalized_msku
                 where c.source_kind='legacy_mirror'
                   and c.updated_by='legacy_mirror'
                   and c.legacy_case_id=e.id
                   and c.is_deleted=false) will_update,
                (select count(*) from enriched e
                 join ops_wfs_fee_anomaly_cases c
                   on c.source_account_ref=e.source_account_ref
                  and c.store_id=e.store_id and c.item_id=e.item_id
                  and c.msku=e.normalized_msku
                 where not (c.source_kind='legacy_mirror'
                   and c.updated_by='legacy_mirror'
                   and c.legacy_case_id=e.id
                   and c.is_deleted=false)) protected_cases,
                (select count(*) from enriched e
                 join ops_wfs_fee_anomaly_cases c
                   on c.source_case_ref = 'legacy_wfs_fee_case:' || e.id::text
                 where c.source_account_ref <> e.source_account_ref
                    or c.store_id <> e.store_id
                    or c.item_id <> e.item_id
                    or c.msku <> e.normalized_msku) case_ref_conflicts
                """
                )
            )
            .mappings()
            .one()
        )
        return WfsFeeLegacySyncResult(
            execute=False,
            legacy_total=int(row["legacy_total"]),
            matched_identities=int(row["matched_identities"]),
            unmatched_identities=int(row["unmatched_identities"]),
            ambiguous_identities=int(row["ambiguous_identities"]),
            duplicate_identities=int(row["duplicate_identities"]),
            invalid_values=int(row["invalid_values"]),
            protected_cases=int(row["protected_cases"]),
            case_ref_conflicts=int(row["case_ref_conflicts"]),
            existing_cases=int(row["existing_cases"]),
            will_insert=int(row["will_insert"]),
            will_update=int(row["will_update"]),
            inserted_or_updated=0,
            status_breakdown={str(k): int(v) for k, v in dict(row["status_breakdown"]).items()},
        )

    def _legacy_upsert_sql(self) -> str:
        id_expr = stable_legacy_uuid_expr("l")
        return (
            LEGACY_IDENTITY_CTE
            + f"""
        insert into ops_wfs_fee_anomaly_cases (
          id, source_kind, source_case_ref, legacy_case_id, legacy_status,
          legacy_updated_at, last_mirrored_at, sync_hash, platform, source_account_ref,
          store_id, item_id, msku, store_name_snapshot, local_sku_snapshot,
          product_name_snapshot, owner_ref, owner_name_snapshot, currency_code,
          manual_unit_fee, actual_unit_fee, unit_fee_diff, fee_source, fee_source_ref,
          fee_calculated_at, calculation_version, affected_units, affected_units_source,
          estimated_recover_amount, estimate_formula, estimate_calculated_at,
          claim_amount, recovered_amount, recovered_at, status, priority, severity,
          status_changed_at, first_alert_at, case_opened_at, done_at, archived_at,
          case_nos, follow_log, latest_follow_note, log_updated_at, archive_requested_by,
          archive_requested_at, archive_reason, archive_review_status, archive_reviewed_by,
          archive_reviewed_at, reason, remark, updated_by, created_at, updated_at, is_deleted
        )
        select
          {id_expr},
          'legacy_mirror',
          'legacy_wfs_fee_case:' || id::text,
          id,
          status,
          updated_at,
          now(),
          sync_hash_value,
          platform,
          source_account_ref,
          store_id,
          item_id,
          trim(msku),
          store_name,
          local_sku,
          product_name,
          owner_ref,
          owner_name,
          'USD',
          manual_fee,
          actual_fee,
          greatest(actual_fee - manual_fee, 0),
          'legacy_case',
          'legacy_wfs_fee_case:' || id::text,
          updated_at,
          'legacy_wfs_case_v1',
          total_units,
          'legacy_total_units',
          est_recover,
          'legacy:(actual_fee-manual_fee)*total_units',
          updated_at,
          claim_amount,
          coalesce(recovered_amount, 0),
          case when status='done' then done_at else null end,
          case status
            when 'waiting' then 'pending_confirm'
            when 'following' then 'following'
            when 'approving' then 'archive_pending'
            when 'closed' then 'archived'
            when 'done' then 'recovered'
            else 'pending_confirm'
          end,
          case when est_recover >= 500 then 'high'
               when est_recover >= 100 then 'medium'
               else 'low' end,
          case when est_recover >= 500 then 'high'
               when est_recover >= 100 then 'medium'
               else 'low' end,
          updated_at,
          first_alert_at,
          case when coalesce(trim(case_nos),'') <> '' then first_alert_at else null end,
          done_at,
          case when status='closed' then coalesce(approved_at, updated_at) else null end,
          nullif(case_nos, ''),
          follow_log,
          nullif(split_part(coalesce(follow_log,''), E'\n', 1), ''),
          log_updated_at,
          nullif(decided_by, ''),
          case when status in ('approving','closed') then updated_at else null end,
          nullif(reason, ''),
          case when status='approving' then 'pending'
               when status='closed' then 'approved'
               else 'none' end,
          nullif(approved_by, ''),
          approved_at,
          nullif(reason, ''),
          nullif(remark, ''),
          'legacy_mirror',
          created_at,
          now(),
          false
        from enriched l
        where true
        on conflict (source_account_ref, store_id, item_id, msku) do update set
          source_kind = excluded.source_kind,
          source_case_ref = excluded.source_case_ref,
          legacy_case_id = excluded.legacy_case_id,
          legacy_status = excluded.legacy_status,
          legacy_updated_at = excluded.legacy_updated_at,
          last_mirrored_at = excluded.last_mirrored_at,
          sync_hash = excluded.sync_hash,
          store_name_snapshot = excluded.store_name_snapshot,
          local_sku_snapshot = excluded.local_sku_snapshot,
          product_name_snapshot = excluded.product_name_snapshot,
          owner_ref = excluded.owner_ref,
          owner_name_snapshot = excluded.owner_name_snapshot,
          manual_unit_fee = excluded.manual_unit_fee,
          actual_unit_fee = excluded.actual_unit_fee,
          unit_fee_diff = excluded.unit_fee_diff,
          affected_units = excluded.affected_units,
          estimated_recover_amount = excluded.estimated_recover_amount,
          claim_amount = excluded.claim_amount,
          recovered_amount = excluded.recovered_amount,
          recovered_at = excluded.recovered_at,
          status = excluded.status,
          priority = excluded.priority,
          severity = excluded.severity,
          status_changed_at = excluded.status_changed_at,
          first_alert_at = excluded.first_alert_at,
          case_opened_at = excluded.case_opened_at,
          done_at = excluded.done_at,
          archived_at = excluded.archived_at,
          case_nos = excluded.case_nos,
          follow_log = excluded.follow_log,
          latest_follow_note = excluded.latest_follow_note,
          log_updated_at = excluded.log_updated_at,
          archive_requested_by = excluded.archive_requested_by,
          archive_requested_at = excluded.archive_requested_at,
          archive_reason = excluded.archive_reason,
          archive_review_status = excluded.archive_review_status,
          archive_reviewed_by = excluded.archive_reviewed_by,
          archive_reviewed_at = excluded.archive_reviewed_at,
          reason = excluded.reason,
          remark = excluded.remark,
          updated_by = excluded.updated_by,
          updated_at = excluded.updated_at,
          is_deleted = false
        where ops_wfs_fee_anomaly_cases.source_kind = 'legacy_mirror'
          and ops_wfs_fee_anomaly_cases.updated_by = 'legacy_mirror'
          and ops_wfs_fee_anomaly_cases.legacy_case_id = excluded.legacy_case_id
        """
        )

    def _case_select_sql(self) -> str:
        return """
        select
          id::text id,
          source_kind,
          source_case_ref,
          legacy_case_id,
          legacy_status,
          legacy_updated_at,
          last_mirrored_at,
          platform,
          source_account_ref,
          store_id,
          item_id,
          msku,
          store_name_snapshot,
          local_sku_snapshot,
          product_name_snapshot,
          owner_ref,
          owner_name_snapshot,
          currency_code,
          manual_unit_fee,
          actual_unit_fee,
          unit_fee_diff,
          fee_source,
          fee_source_ref,
          fee_calculated_at,
          calculation_version,
          affected_units,
          affected_sales_start_date,
          affected_sales_end_date,
          affected_units_source,
          estimated_recover_amount,
          greatest(estimated_recover_amount - recovered_amount, 0) pending_recover_amount,
          claim_amount,
          recovered_amount,
          recovered_at,
          status,
          priority,
          severity,
          status_changed_at,
          status_changed_by,
          first_alert_at,
          case_opened_at,
          done_at,
          archived_at,
          case_nos,
          follow_log,
          latest_follow_note,
          log_updated_at,
          next_follow_at,
          follow_count,
          last_follow_by,
          last_follow_at,
          walmart_response_summary,
          last_rejection_reason,
          evidence_summary,
          archive_requested_by,
          archive_requested_at,
          archive_reason_type,
          archive_reason,
          archive_evidence,
          archive_review_status,
          archive_reviewed_by,
          archive_reviewed_at,
          archive_review_note,
          reason,
          remark,
          internal_note,
          created_at,
          updated_at,
          updated_by
        from ops_wfs_fee_anomaly_cases
        """
