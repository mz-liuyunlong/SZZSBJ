"""结算利润 PR-2：财务发货单（shippingList v2）与发货单明细（shippingDetail）同步。

发货单：一个店、一个时间窗（按发货时间）offset/length 翻页，写 ods_lingxing_fin_shipping_lists
（当前状态，按 发货单号 upsert）。
明细：从发货单表挑「已发货、在时间窗内、明细还没拉过（detail_synced_at 为空）或发货单变过
（detail_synced_at 早于 updated_at）」的单子，一张一次请求，
写 ods_lingxing_fin_shipping_detail_items（发货单 × MSKU，upsert；
新明细里没有的 MSKU 同一事务删掉），并在发货单上记 detail_synced_at（明细为空也记，不反复重拉）。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from functools import partial
from typing import Any, Protocol

from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.integrations.lingxing.client import LingxingRawEnvelope
from app.modules.integration_sync.fin_shipping_catalog import (
    FIN_SHIPPING_DETAIL_SYNC_SPEC,
    FIN_SHIPPING_LIST_SYNC_SPEC,
)
from app.modules.integration_sync.handlers.lingxing_fin_sync_base import (
    SHANGHAI,
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
from app.modules.settlement_profit.models import FinShippingDetailItem, FinShippingList
from app.modules.warehouse_wfs.store_discovery import WfsSettlementStore

logger = logging.getLogger(__name__)

SHIPPED_STATUS = "2"  # shippingListStatus 2 = 已发货


class FinShippingListPageClient(Protocol):
    def fetch_fin_shipping_list_page(
        self,
        *,
        store_id: str,
        offset: int,
        length: int,
        page_no: int,
        start_date: date,
        end_date: date,
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
    ) -> LingxingRawEnvelope: ...


class FinShippingDetailClient(Protocol):
    def fetch_fin_shipping_detail(
        self,
        *,
        store_id: str,
        shipping_list_code: str,
        source_account_ref: str,
        run_id: str,
        work_item_id: str,
    ) -> LingxingRawEnvelope: ...


# --------------------------------------------------------------------------- 解析


def parse_shipping_list_row(
    row: dict[str, Any], *, store_id: str, source_account_ref: str
) -> dict[str, Any] | None:
    """一行发货单 → 表字段；没有发货单号返回 None（整页按脏数据失败）。"""
    code = text_or_none(row.get("shippingListCode"), 64)
    if code is None:
        return None
    status = row.get("shippingListStatus")
    return {
        "source_account_ref": source_account_ref,
        "store_id": store_id,
        "shipping_list_code": code,
        "shipping_list_status": text_or_none(status, 32),
        "logistics_provider_id": text_or_none(row.get("logisticsProviderId"), 64),
        "logistics_provider_name": text_or_none(row.get("logisticsProviderName"), 4000),
        "logistics_channel_name": text_or_none(row.get("logisticsChannelName"), 4000),
        "head_fee_type": None,
        "warehouse_id": text_or_none(row.get("warehouseId"), 64),
        "delivery_at": lx_datetime(row.get("deliveryTime")),
        "lx_created_at": lx_datetime(row.get("gmtCreate")),
        "row_hash": row_hash(row),
        "raw_row": row,
    }


def parse_shipping_detail_items(
    items: list[dict[str, Any]],
    *,
    shipping_list_code: str,
    default_store_id: str,
    source_account_ref: str,
) -> list[dict[str, Any]]:
    """firstLetListResponseList → 明细行；同一 MSKU 出现多次就把发货量加起来（单价取第一条）。"""
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        msku = text_or_none(item.get("msku"), 4000)
        if msku is None:
            continue
        existing = merged.get(msku)
        if existing is not None:
            qty = decimal_or_none(item.get("deliveryNum"))
            if qty is not None:
                existing["delivery_num"] = (existing["delivery_num"] or 0) + qty
            existing["raw_row"]["merged_rows"] = existing["raw_row"].get("merged_rows", 1) + 1
            existing["raw_row"]["merged_delivery_num"] = str(existing["delivery_num"])
            # 行指纹按合并后的结果算，第二条的数量变了指纹也要变。
            existing["row_hash"] = row_hash(existing["raw_row"])
            continue
        merged[msku] = {
            "source_account_ref": source_account_ref,
            "store_id": text_or_none(item.get("storeId"), 32) or default_store_id,
            "shipping_list_code": shipping_list_code,
            "msku": msku,
            "sku": text_or_none(item.get("sku"), 4000),
            "gtin": text_or_none(item.get("gtin"), 64),
            "purchase_price": decimal_or_none(item.get("purchasePrice")),
            "head_stock_price": decimal_or_none(item.get("headStockPrice")),
            "per_firstlet_cost": decimal_or_none(item.get("perFirstletCost")),
            "per_firstlet_actual": decimal_or_none(item.get("perFirstletActual")),
            "per_firstlet_expected": decimal_or_none(item.get("perFirstletExpected")),
            "per_tax": decimal_or_none(item.get("perTax")),
            "wfs_stock_price": decimal_or_none(item.get("wfsStockPrice")),
            "other_cost": decimal_or_none(item.get("otherCost")),
            "transportation_cost": decimal_or_none(item.get("transportationCost")),
            "currency_code": _currency(item.get("totalCostCurrency")),
            "logistics_way": text_or_none(item.get("logisticsWay"), 4000),
            "logistics_provider_id": None,
            "head_fee_type": text_or_none(item.get("headFeeTypeStr"), 32),
            "value_source": text_or_none(item.get("valueSourceStr"), 32),
            "delivery_num": decimal_or_none(item.get("deliveryNum")),
            "row_hash": row_hash(item),
            "raw_row": dict(item),
        }
    return list(merged.values())


def _currency(value: object) -> str | None:
    """领星只给货币符号（￥/$）；能认出来的转成代码，认不出来留空。"""
    symbol = text_or_none(value, 8)
    if symbol in {"￥", "¥", "CNY"}:
        return "CNY"
    if symbol in {"$", "USD"}:
        return "USD"
    return None


# --------------------------------------------------------------------------- 发货单


class LingxingFinShippingListSyncHandler(FinSyncHandlerBase):
    spec = FIN_SHIPPING_LIST_SYNC_SPEC
    handler_key = FIN_SHIPPING_LIST_SYNC_SPEC.handler_key

    def _sync_store(
        self,
        run: IntegrationSyncRun,
        client: FinShippingListPageClient,
        policy: RawRetentionPolicy,
        store: WfsSettlementStore,
        start: date,
        end: date,
        page_size: int,
        max_pages: int,
    ) -> None:
        offset = 0
        previous_codes: set[str] = set()
        for page_no in range(1, max_pages + 1):
            work = self._start_work_item(
                run,
                scope_key=f"{store.store_id}:{start.isoformat()}:{end.isoformat()}:{page_no}",
                safe_params={
                    "storeIds": [store.store_id],
                    "timeField": 2,
                    "startTime": start.isoformat(),
                    "endTime": end.isoformat(),
                    "offset": offset,
                    "length": page_size,
                },
                offset=offset,
                length=page_size,
            )
            payload, ref = self._fetch_and_store(
                run,
                work,
                policy,
                partial(
                    client.fetch_fin_shipping_list_page,
                    store_id=store.store_id,
                    offset=offset,
                    length=page_size,
                    page_no=page_no,
                    start_date=start,
                    end_date=end,
                    source_account_ref=run.source_account_ref,
                    run_id=str(run.id),
                    work_item_id=str(work.id),
                ),
            )
            rows = response_list(payload, "data", "list")
            if rows is None:
                self._fail_work(run, work, "SYNC_FIN_SHIPPING_RESPONSE_SHAPE")
                raise FinSyncError("SYNC_FIN_SHIPPING_RESPONSE_SHAPE")
            values = [
                parse_shipping_list_row(
                    row, store_id=store.store_id, source_account_ref=run.source_account_ref
                )
                for row in rows
            ]
            if any(value is None for value in values):
                self._fail_work(run, work, "SYNC_FIN_SHIPPING_INVALID_ROW")
                raise FinSyncError("SYNC_FIN_SHIPPING_INVALID_ROW")
            codes = {value["shipping_list_code"] for value in values if value is not None}
            if codes and codes == previous_codes:
                # 领星没理会 offset、一直返回同一页：立刻停，不白跑到 max_pages。
                self._fail_work(run, work, "SYNC_FIN_SHIPPING_PAGE_REPEATED")
                raise FinSyncError("SYNC_FIN_SHIPPING_PAGE_REPEATED")
            previous_codes = codes
            written = _upsert_shipping_lists(
                self.session, [value for value in values if value is not None], run, ref
            )
            self._finish_work(run, work, ref, seen=len(rows), written=written)
            total = response_total(payload, "data", "total")
            offset += len(rows)
            if not rows or (total is not None and offset >= total):
                return
        raise FinSyncError("SYNC_FIN_SHIPPING_TOO_MANY_PAGES")


def _upsert_shipping_lists(
    session: Session,
    values: list[dict[str, Any]],
    run: IntegrationSyncRun,
    ref: ApiRawRequestRef,
) -> int:
    if not values:
        return 0
    # 同一页里同一张发货单出现两次只留最后一条，避免 ON CONFLICT 撞自己。
    unique = {value["shipping_list_code"]: value for value in values}
    now = utc_now()
    statement = pg_insert(FinShippingList).values(
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
    # detail_synced_at 归明细同步管，发货单 upsert 不碰它（#370 第二轮复核 P2-1）。
    keep = {
        "id",
        "source_account_ref",
        "store_id",
        "shipping_list_code",
        "created_at",
        "detail_synced_at",
    }
    set_ = {
        column.name: excluded[column.name]
        for column in FinShippingList.__table__.columns
        if column.name not in keep and column.name != "updated_at"
    }
    # 发货单内容没变就不动 updated_at：明细同步靠它判断「发货单变过、明细要重拉」。
    set_["updated_at"] = case(
        (FinShippingList.row_hash != excluded.row_hash, excluded.updated_at),
        else_=FinShippingList.updated_at,
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["source_account_ref", "store_id", "shipping_list_code"],
            set_=set_,
        )
    )
    return len(unique)


# --------------------------------------------------------------------------- 明细


class LingxingFinShippingDetailSyncHandler(FinSyncHandlerBase):
    spec = FIN_SHIPPING_DETAIL_SYNC_SPEC
    handler_key = FIN_SHIPPING_DETAIL_SYNC_SPEC.handler_key

    def _sync_store(
        self,
        run: IntegrationSyncRun,
        client: FinShippingDetailClient,
        policy: RawRetentionPolicy,
        store: WfsSettlementStore,
        start: date,
        end: date,
        page_size: int,
        max_pages: int,
    ) -> None:
        del page_size
        codes = pending_detail_codes(
            self.session,
            source_account_ref=run.source_account_ref,
            store_id=store.store_id,
            start=start,
            end=end,
            limit=max_pages,
        )
        if len(codes) >= max_pages:
            logger.warning(
                "fin shipping detail backlog reaches max_pages=%s for one store", max_pages
            )
        for ordinal, code in enumerate(codes, start=1):
            work = self._start_work_item(
                run,
                scope_key=f"{store.store_id}:{code}",
                safe_params={"shippingListCode": code, "ordinal": ordinal},
                offset=0,
                length=1,
            )
            payload, ref = self._fetch_and_store(
                run,
                work,
                policy,
                partial(
                    client.fetch_fin_shipping_detail,
                    store_id=store.store_id,
                    shipping_list_code=code,
                    source_account_ref=run.source_account_ref,
                    run_id=str(run.id),
                    work_item_id=str(work.id),
                ),
            )
            items = response_list(payload, "data", "firstLetListResponseList")
            if items is None:
                self._fail_work(run, work, "SYNC_FIN_SHIPPING_RESPONSE_SHAPE")
                raise FinSyncError("SYNC_FIN_SHIPPING_RESPONSE_SHAPE")
            values = parse_shipping_detail_items(
                items,
                shipping_list_code=code,
                default_store_id=store.store_id,
                source_account_ref=run.source_account_ref,
            )
            written = _replace_detail_items(
                self.session,
                values,
                run,
                ref,
                source_account_ref=run.source_account_ref,
                store_id=store.store_id,
                shipping_list_code=code,
            )
            self._finish_work(run, work, ref, seen=len(items), written=written)


def pending_detail_codes(
    session: Session,
    *,
    source_account_ref: str,
    store_id: str,
    start: date,
    end: date,
    limit: int,
) -> list[str]:
    """已发货、发货时间在窗内、且（明细没拉过 或 发货单在明细之后变过）的发货单号，新的在前。"""
    window_start = datetime.combine(start, datetime.min.time(), tzinfo=SHANGHAI)
    window_end = datetime.combine(end, datetime.max.time(), tzinfo=SHANGHAI)
    statement = (
        select(FinShippingList.shipping_list_code)
        .where(
            FinShippingList.source_account_ref == source_account_ref,
            FinShippingList.store_id == store_id,
            FinShippingList.shipping_list_status == SHIPPED_STATUS,
            FinShippingList.delivery_at.is_not(None),
            FinShippingList.delivery_at >= window_start,
            FinShippingList.delivery_at <= window_end,
            FinShippingList.detail_synced_at.is_(None)
            | (FinShippingList.detail_synced_at < FinShippingList.updated_at),
        )
        .order_by(FinShippingList.delivery_at.desc(), FinShippingList.shipping_list_code)
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def _replace_detail_items(
    session: Session,
    values: list[dict[str, Any]],
    run: IntegrationSyncRun,
    ref: ApiRawRequestRef,
    *,
    source_account_ref: str,
    store_id: str,
    shipping_list_code: str,
) -> int:
    """同一事务：upsert 新明细、删掉这张单不在新集合里的 MSKU 行、在发货单上记 detail_synced_at。"""
    now = utc_now()
    mskus = [value["msku"] for value in values]
    stale = delete(FinShippingDetailItem).where(
        FinShippingDetailItem.source_account_ref == source_account_ref,
        FinShippingDetailItem.shipping_list_code == shipping_list_code,
    )
    if mskus:
        stale = stale.where(FinShippingDetailItem.msku.not_in(mskus))
    session.execute(stale)
    written = _upsert_detail_items(session, values, run, ref, now)
    session.execute(
        update(FinShippingList)
        .where(
            FinShippingList.source_account_ref == source_account_ref,
            FinShippingList.store_id == store_id,
            FinShippingList.shipping_list_code == shipping_list_code,
        )
        .values(detail_synced_at=now)
    )
    return written


def _upsert_detail_items(
    session: Session,
    values: list[dict[str, Any]],
    run: IntegrationSyncRun,
    ref: ApiRawRequestRef,
    now: datetime,
) -> int:
    if not values:
        return 0
    statement = pg_insert(FinShippingDetailItem).values(
        [
            {
                **value,
                "source_run_id": run.id,
                "source_raw_request_ref_id": ref.id,
                "synced_at": now,
                "updated_at": now,
            }
            for value in values
        ]
    )
    excluded = statement.excluded
    keep = {"id", "source_account_ref", "shipping_list_code", "msku", "created_at"}
    set_ = {
        column.name: excluded[column.name]
        for column in FinShippingDetailItem.__table__.columns
        if column.name not in keep
    }
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["source_account_ref", "shipping_list_code", "msku"],
            set_=set_,
        )
    )
    return len(values)
