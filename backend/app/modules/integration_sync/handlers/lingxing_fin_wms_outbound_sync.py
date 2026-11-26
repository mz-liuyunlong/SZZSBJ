"""结算利润 PR-2：销售出库单（wmsOrderList）同步，给非 WFS 自发货订单的尾程物流费用。

一个店、一个时间窗（按变更时间 update_at）page/page_size 翻页，
写 ods_lingxing_fin_wms_outbound_orders（当前状态，按 出库单号 upsert）。
收件人等个人信息在落原始层之前就删掉（见 lingxing_fin_sync_base.scrub_pii）。
"""

from __future__ import annotations

from datetime import date
from functools import partial
from typing import Any, Protocol

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.integrations.lingxing.client import LingxingRawEnvelope
from app.modules.integration_sync.fin_shipping_catalog import FIN_WMS_OUTBOUND_SYNC_SPEC
from app.modules.integration_sync.handlers.lingxing_fin_sync_base import (
    FinSyncError,
    FinSyncHandlerBase,
    decimal_or_none,
    lx_datetime,
    response_list,
    response_total,
    row_hash,
    text_or_none,
    utc_now,
)
from app.modules.integration_sync.models import (
    ApiRawRequestRef,
    IntegrationSyncRun,
    RawRetentionPolicy,
)
from app.modules.settlement_profit.models import FinWmsOutboundOrder
from app.modules.warehouse_wfs.store_discovery import WfsSettlementStore

# 明细只留计算要用的键；其余在原始层里。
_ITEM_KEYS = (
    "wod_id",
    "seller_sku",
    "sku",
    "count",
    "platform_order_no",
    "item_unit_price",
    "item_total_price",
    "currency_code",
    "apportion_freight",
    "apportion_freight_single",
    "logistics_freight_currency_code",
    "stock_cost",
    "bundle_type",
)


class FinWmsOrderPageClient(Protocol):
    def fetch_fin_wms_order_page(
        self,
        *,
        store_id: str,
        page_no: int,
        page_size: int,
        start_date: date,
        end_date: date,
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
    ) -> LingxingRawEnvelope: ...


def parse_wms_order_row(
    row: dict[str, Any], *, store_id: str, source_account_ref: str
) -> dict[str, Any] | None:
    """一行出库单 → 表字段；没有出库单号、或 sid 不是请求的店，返回 None（整页按脏数据失败）。"""
    order_no = text_or_none(row.get("wo_number"), 64)
    if order_no is None:
        return None
    # 请求按 sid_arr=[store_id] 一次一店；返回行带 sid 时必须等于请求的店（#370 复审 P1）。
    row_sid = text_or_none(row.get("sid"), 32)
    if row_sid is not None and row_sid != store_id:
        return None
    platform_orders = row.get("platform_order_no")
    if isinstance(platform_orders, list):
        platform_order_no = text_or_none(platform_orders[0], 64) if platform_orders else None
    else:
        platform_order_no = text_or_none(platform_orders, 64)
    items_raw = row.get("product_info")
    items = (
        [
            {key: item.get(key) for key in _ITEM_KEYS if key in item}
            for item in items_raw
            if isinstance(item, dict)
        ]
        if isinstance(items_raw, list)
        else []
    )
    raw = {key: value for key, value in row.items() if key != "product_info"}
    return {
        "source_account_ref": source_account_ref,
        "store_id": store_id,
        "outbound_order_no": order_no,
        "platform_order_no": platform_order_no,
        "order_status": (
            text_or_none(row.get("status_name"), 32) or text_or_none(row.get("status"), 32)
        ),
        "logistics_fee": decimal_or_none(row.get("logistics_freight")),
        "currency_code": text_or_none(row.get("logistics_freight_currency_code"), 3),
        "outbound_at": (
            lx_datetime(row.get("delivered_at")) or lx_datetime(row.get("stock_delivered_at"))
        ),
        "items": items,
        "row_hash": row_hash(row),
        "raw_row": raw,
    }


class LingxingFinWmsOutboundSyncHandler(FinSyncHandlerBase):
    spec = FIN_WMS_OUTBOUND_SYNC_SPEC
    handler_key = FIN_WMS_OUTBOUND_SYNC_SPEC.handler_key

    def _sync_store(
        self,
        run: IntegrationSyncRun,
        client: FinWmsOrderPageClient,
        policy: RawRetentionPolicy,
        store: WfsSettlementStore,
        start: date,
        end: date,
        page_size: int,
        max_pages: int,
    ) -> None:
        seen_total = 0
        previous_codes: set[str] = set()
        for page_no in range(1, max_pages + 1):
            work = self._start_work_item(
                run,
                scope_key=f"{store.store_id}:{start.isoformat()}:{end.isoformat()}:{page_no}",
                safe_params={
                    "sid_arr": [store.store_id],
                    "time_type": "update_at",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "page": page_no,
                    "page_size": page_size,
                },
                offset=(page_no - 1) * page_size,
                length=page_size,
            )
            payload, ref = self._fetch_and_store(
                run,
                work,
                policy,
                partial(
                    client.fetch_fin_wms_order_page,
                    store_id=store.store_id,
                    page_no=page_no,
                    page_size=page_size,
                    start_date=start,
                    end_date=end,
                    source_account_ref=run.source_account_ref,
                    run_id=str(run.id),
                    work_item_id=str(work.id),
                ),
            )
            rows = response_list(payload, "data")
            if rows is None:
                self._fail_work(run, work, "SYNC_FIN_WMS_RESPONSE_SHAPE")
                raise FinSyncError("SYNC_FIN_WMS_RESPONSE_SHAPE")
            values = [
                parse_wms_order_row(
                    row, store_id=store.store_id, source_account_ref=run.source_account_ref
                )
                for row in rows
            ]
            if any(value is None for value in values):
                self._fail_work(run, work, "SYNC_FIN_WMS_INVALID_ROW")
                raise FinSyncError("SYNC_FIN_WMS_INVALID_ROW")
            codes = {value["outbound_order_no"] for value in values if value is not None}
            if codes and codes == previous_codes:
                # 领星没理会 page、一直返回同一页：立刻停，不白跑到 max_pages。
                self._fail_work(run, work, "SYNC_FIN_WMS_PAGE_REPEATED")
                raise FinSyncError("SYNC_FIN_WMS_PAGE_REPEATED")
            previous_codes = codes
            total = response_total(payload, "total")
            if not rows and total is not None and seen_total < total:
                # 领星说还有，却给了空页：数据没拉齐，这页和这家店都不能记成功。
                self._fail_work(run, work, "SYNC_FIN_WMS_INCOMPLETE")
                raise FinSyncError("SYNC_FIN_WMS_INCOMPLETE")
            written = _upsert_wms_orders(
                self.session, [value for value in values if value is not None], run, ref
            )
            self._finish_work(run, work, ref, seen=len(rows), written=written)
            seen_total += len(rows)
            if not rows or (total is not None and seen_total >= total):
                return
        raise FinSyncError("SYNC_FIN_WMS_TOO_MANY_PAGES")


def _upsert_wms_orders(
    session: Session,
    values: list[dict[str, Any]],
    run: IntegrationSyncRun,
    ref: ApiRawRequestRef,
) -> int:
    if not values:
        return 0
    # 同一页里同一张出库单出现两次（接口翻页抖动）只留最后一条，避免 ON CONFLICT 撞自己。
    unique: dict[str, dict[str, Any]] = {value["outbound_order_no"]: value for value in values}
    now = utc_now()
    statement = pg_insert(FinWmsOutboundOrder).values(
        [
            {
                **value,
                "source_run_id": run.id,
                "source_raw_request_ref_id": ref.id,
                "synced_at": now,
                "updated_at": now,
            }
            for value in unique.values()
        ]
    )
    excluded = statement.excluded
    keep = {"id", "source_account_ref", "store_id", "outbound_order_no", "created_at"}
    set_ = {
        column.name: excluded[column.name]
        for column in FinWmsOutboundOrder.__table__.columns
        if column.name not in keep
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["source_account_ref", "store_id", "outbound_order_no"],
            set_=set_,
        )
    )
    return len(unique)
