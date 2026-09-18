from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.warehouse_wfs.schemas import (
    WfsFeeActualWrite,
    WfsFeeActualWriteResult,
    WfsFeeAlertListData,
    WfsFeeAlertQuery,
    WfsFeeAlertRead,
    WfsFeeCaseWrite,
)


class WfsFeeAlertService:
    """Reconcile Product Management WFS expectations with actual Walmart fee facts."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_alerts(
        self,
        query: WfsFeeAlertQuery,
        account_refs: frozenset[str],
    ) -> tuple[WfsFeeAlertListData, int]:
        where = [
            "m.source_account_ref = any(:accounts)",
            "m.wfs_fee_actual_total_amount is not null",
            "coalesce(m.wfs_fee_variance_amount,0) > 0",
        ]
        params: dict[str, object] = {"accounts": list(account_refs)}
        if query.start_date is not None:
            where.append("m.business_date_la >= :start_date")
            params["start_date"] = query.start_date
        if query.end_date is not None:
            where.append("m.business_date_la <= :end_date")
            params["end_date"] = query.end_date
        if query.store_id is not None:
            where.append("m.store_id = :store_id")
            params["store_id"] = query.store_id
        if query.owner_ref is not None:
            where.append("m.owner_ref = :owner_ref")
            params["owner_ref"] = query.owner_ref
        if query.status is not None:
            where.append("coalesce(c.status,'未开Case') = :status")
            params["status"] = query.status
        if query.keyword:
            where.append(
                "(m.local_sku ilike :keyword or m.msku ilike :keyword or "
                "m.item_id ilike :keyword or m.local_name ilike :keyword or m.title ilike :keyword)"
            )
            params["keyword"] = f"%{query.keyword}%"
        where_sql = " and ".join(where)
        total = int(
            self.session.execute(
                text(
                    "select count(*) from mart_daily_sales_item_day m "
                    "left join ops_wfs_fee_anomaly_cases c "
                    "on c.source_account_ref=m.source_account_ref "
                    "and c.business_date_la=m.business_date_la and c.store_id=m.store_id "
                    "and c.item_id=m.item_id and trim(c.msku)=trim(m.msku) where " + where_sql
                ),
                params,
            ).scalar_one()
        )
        params.update({"limit": query.page_size, "offset": (query.page - 1) * query.page_size})
        rows = (
            self.session.execute(
                text(
                    "select m.id,m.business_date_la,m.store_id,m.store_name,m.owner_ref,m.item_id,m.msku,"
                    "m.local_sku,coalesce(m.local_name,m.title) product_name,m.order_count,m.sales_qty,"
                    "m.cost_quantity,m.wfs_fee_expected_total_amount expected_fee_amount,"
                    "m.wfs_fee_actual_total_amount actual_fee_amount,"
                    "m.wfs_fee_variance_amount variance_amount,"
                    "m.wfs_fee_variance_rate variance_rate,"
                    "m.wfs_fee_expected_unit_amount expected_unit_amount,"
                    "case when m.cost_quantity>0 then "
                    "m.wfs_fee_actual_total_amount/m.cost_quantity end actual_unit_amount,"
                    "coalesce(c.status,'未开Case') status,c.case_no,c.reason,"
                    "coalesce(c.priority,'中') priority,"
                    "c.claim_amount,coalesce(c.recovered_amount,0) recovered_amount,"
                    "c.case_opened_at,"
                    "c.next_follow_at,c.latest_follow "
                    "from mart_daily_sales_item_day m "
                    "left join ops_wfs_fee_anomaly_cases c "
                    "on c.source_account_ref=m.source_account_ref "
                    "and c.business_date_la=m.business_date_la "
                    "and c.store_id=m.store_id and c.item_id=m.item_id "
                    "and trim(c.msku)=trim(m.msku) "
                    "where "
                    + where_sql
                    + " order by m.wfs_fee_variance_amount desc,m.business_date_la desc "
                    "limit :limit offset :offset"
                ),
                params,
            )
            .mappings()
            .all()
        )
        items = []
        for row in rows:
            variance = row["variance_amount"] or Decimal("0")
            recovered = row["recovered_amount"] or Decimal("0")
            items.append(
                WfsFeeAlertRead(
                    **dict(row),
                    pending_recovery_amount=max(variance - recovered, Decimal("0")),
                )
            )
        return WfsFeeAlertListData(items=items), total

    def write_actual(
        self,
        payload: WfsFeeActualWrite,
        account_refs: frozenset[str],
    ) -> WfsFeeActualWriteResult:
        if payload.source_account_ref not in account_refs:
            raise ApiError(code=ErrorCode.FORBIDDEN, status_code=403)
        matched = self.session.execute(
            text(
                "select count(*) from dim_walmart_listings where source_account_ref=:account "
                "and store_id=:store_id and item_id=:item_id and trim(msku)=trim(:msku)"
            ),
            {
                "account": payload.source_account_ref,
                "store_id": payload.store_id,
                "item_id": payload.item_id,
                "msku": payload.msku,
            },
        ).scalar_one()
        if int(matched or 0) != 1:
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
        now = datetime.now(UTC)
        self.session.execute(
            text(
                "insert into fact_walmart_wfs_fee_actual "
                "(id,source_account_ref,business_date_la,store_id,item_id,msku,source_line_ref,"
                "actual_fee_amount,currency_code,source_type,source_observed_at,"
                "created_at,updated_at) "
                "values (:id,:account,:day,:store_id,:item_id,:msku,:source_line_ref,"
                ":actual_fee_amount,"
                ":currency_code,:source_type,:source_observed_at,:now,:now) "
                "on conflict (source_account_ref,source_line_ref) do update set "
                "business_date_la=excluded.business_date_la,store_id=excluded.store_id,"
                "item_id=excluded.item_id,"
                "msku=excluded.msku,actual_fee_amount=excluded.actual_fee_amount,"
                "currency_code=excluded.currency_code,"
                "source_type=excluded.source_type,"
                "source_observed_at=excluded.source_observed_at,"
                "updated_at=excluded.updated_at"
            ),
            {
                "id": str(uuid4()),
                "account": payload.source_account_ref,
                "day": payload.business_date_la,
                "store_id": payload.store_id,
                "item_id": payload.item_id,
                "msku": payload.msku,
                "source_line_ref": payload.source_line_ref,
                "actual_fee_amount": payload.actual_fee_amount,
                "currency_code": payload.currency_code,
                "source_type": payload.source_type,
                "source_observed_at": payload.source_observed_at,
                "now": now,
            },
        )
        result = self.session.execute(
            text(
                "with actual as (select sum(actual_fee_amount) total "
                "from fact_walmart_wfs_fee_actual "
                "where source_account_ref=:account and business_date_la=:day "
                "and store_id=:store_id "
                "and item_id=:item_id and trim(msku)=trim(:msku)) "
                "update mart_daily_sales_item_day m set "
                "wfs_fee_actual_total_amount=actual.total,"
                "wfs_fee_variance_amount=actual.total-m.wfs_fee_expected_total_amount,"
                "wfs_fee_variance_rate=case when m.wfs_fee_expected_total_amount>0 "
                "then (actual.total-m.wfs_fee_expected_total_amount)"
                "/m.wfs_fee_expected_total_amount end,"
                "wfs_fee_source='walmart_statement',wfs_fee_total_amount=actual.total,"
                "gross_profit_amount=case when m.purchase_cost_total_usd is not null "
                "and m.first_leg_cost_total_usd is not null "
                "and m.storage_fee_total_amount is not null "
                "then m.sales_amount-coalesce(m.ad_spend_amount,0)"
                "-coalesce(m.commission_fee_amount,0)-actual.total "
                "-m.purchase_cost_total_usd-m.first_leg_cost_total_usd"
                "-m.storage_fee_total_amount end,"
                "gross_margin=case when m.sales_amount>0 and m.purchase_cost_total_usd is not null "
                "and m.first_leg_cost_total_usd is not null "
                "and m.storage_fee_total_amount is not null "
                "then (m.sales_amount-coalesce(m.ad_spend_amount,0)"
                "-coalesce(m.commission_fee_amount,0)-actual.total "
                "-m.purchase_cost_total_usd-m.first_leg_cost_total_usd"
                "-m.storage_fee_total_amount)/m.sales_amount end,"
                "roi=case when coalesce(m.purchase_cost_total_usd,0)"
                "+coalesce(m.first_leg_cost_total_usd,0)>0 "
                "and m.purchase_cost_total_usd is not null "
                "and m.first_leg_cost_total_usd is not null "
                "and m.storage_fee_total_amount is not null "
                "then (m.sales_amount-coalesce(m.ad_spend_amount,0)"
                "-coalesce(m.commission_fee_amount,0)-actual.total "
                "-m.purchase_cost_total_usd-m.first_leg_cost_total_usd"
                "-m.storage_fee_total_amount)"
                "/(m.purchase_cost_total_usd+m.first_leg_cost_total_usd) end,updated_at=:now "
                "from actual where m.source_account_ref=:account and m.business_date_la=:day "
                "and m.store_id=:store_id and m.item_id=:item_id and trim(m.msku)=trim(:msku)"
            ),
            {
                "account": payload.source_account_ref,
                "day": payload.business_date_la,
                "store_id": payload.store_id,
                "item_id": payload.item_id,
                "msku": payload.msku,
                "now": now,
            },
        )
        self.session.commit()
        return WfsFeeActualWriteResult(
            source_line_ref=payload.source_line_ref,
            mart_updated=bool(result.rowcount),
        )

    def update_case(
        self,
        mart_id: UUID,
        payload: WfsFeeCaseWrite,
        account_refs: frozenset[str],
        actor_ref: str,
    ) -> None:
        identity = (
            self.session.execute(
                text(
                    "select source_account_ref,business_date_la,store_id,item_id,msku "
                    "from mart_daily_sales_item_day where id=:id "
                    "and source_account_ref=any(:accounts)"
                ),
                {"id": str(mart_id), "accounts": list(account_refs)},
            )
            .mappings()
            .first()
        )
        if identity is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        now = datetime.now(UTC)
        self.session.execute(
            text(
                "insert into ops_wfs_fee_anomaly_cases "
                "(id,source_account_ref,business_date_la,store_id,item_id,msku,status,case_no,reason,priority,"
                "claim_amount,recovered_amount,case_opened_at,next_follow_at,"
                "latest_follow,updated_by,created_at,updated_at) "
                "values (:id,:account,:day,:store_id,:item_id,:msku,:status,"
                ":case_no,:reason,:priority,"
                ":claim_amount,:recovered_amount,:case_opened_at,:next_follow_at,"
                ":latest_follow,:updated_by,:now,:now) "
                "on conflict (source_account_ref,business_date_la,store_id,item_id,msku) "
                "do update set "
                "status=excluded.status,case_no=excluded.case_no,"
                "reason=excluded.reason,priority=excluded.priority,"
                "claim_amount=excluded.claim_amount,"
                "recovered_amount=excluded.recovered_amount,"
                "case_opened_at=excluded.case_opened_at,"
                "next_follow_at=excluded.next_follow_at,"
                "latest_follow=excluded.latest_follow,updated_by=excluded.updated_by,"
                "updated_at=excluded.updated_at"
            ),
            {
                "id": str(uuid4()),
                "account": identity["source_account_ref"],
                "day": identity["business_date_la"],
                "store_id": identity["store_id"],
                "item_id": identity["item_id"],
                "msku": identity["msku"],
                "status": payload.status,
                "case_no": payload.case_no or None,
                "reason": payload.reason or None,
                "priority": payload.priority,
                "claim_amount": payload.claim_amount,
                "recovered_amount": payload.recovered_amount,
                "case_opened_at": payload.case_opened_at,
                "next_follow_at": payload.next_follow_at,
                "latest_follow": payload.latest_follow or None,
                "updated_by": actor_ref,
                "now": now,
            },
        )
        self.session.commit()
