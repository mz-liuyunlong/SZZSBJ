from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import StringIO

from sqlalchemy.orm import Session

from app.modules.data_pages.models import (
    DailySalesItemDayMart,
    ListingManagementCurrentMart,
    OrderProfitSkuDayMart,
)
from app.modules.data_pages.repository import (
    DailySalesRepository,
    ListingManagementRepository,
    ListingTagRepository,
    OrderProfitRepository,
)
from app.modules.data_pages.schemas import (
    DailySalesItemRead,
    DailySalesListData,
    DailySalesQuery,
    DailySalesSummaryRead,
    DailySalesTrendPointRead,
    DataPageFilterOptionRead,
    DataPageFilterOptionsData,
    ListingArchiveActionData,
    ListingGptAnalysisLinkRead,
    ListingGptAnalysisLinkUpdateRequest,
    ListingManagementFilterOptionsData,
    ListingManagementItemRead,
    ListingManagementListData,
    ListingManagementQuery,
    ListingManagementSummaryData,
    ListingTagBatchSetData,
    ListingTagBatchSetRequest,
    ListingTagCreateRequest,
    ListingTagListData,
    ListingTagRead,
    ListingTagUpdateRequest,
    OrderProfitItemRead,
    OrderProfitListData,
    OrderProfitQuery,
    OrderProfitSummaryRead,
    OrderProfitTrendData,
    OrderProfitTrendPointRead,
)


def _decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value)


def _percent_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if not denominator:
        return None
    return (numerator / denominator * Decimal("100")).quantize(Decimal("0.000001"))


def _refund_loss_amount(
    refund_amount: object,
    commission_rate: object,
) -> Decimal | None:
    amount = _optional_decimal(refund_amount)
    if amount is None:
        return None
    rate = _decimal(commission_rate)
    return max(amount * (Decimal("1") - rate), Decimal("0"))


def _trend_points(value: object) -> list[DailySalesTrendPointRead]:
    if not isinstance(value, list):
        return []
    result: list[DailySalesTrendPointRead] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        raw_date = item.get("date") or item.get("business_date")
        if raw_date is None:
            continue
        try:
            point_date = date.fromisoformat(str(raw_date))
        except ValueError:
            continue
        result.append(
            DailySalesTrendPointRead(
                date=point_date,
                sales_qty=_decimal(
                    item.get("sales_qty") or item.get("value") or item.get("quantity")
                ),
            )
        )
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _tag_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            tags.append(item.strip())
        elif isinstance(item, dict):
            label = item.get("label") or item.get("name") or item.get("title")
            if label is not None and str(label).strip():
                tags.append(str(label).strip())
    return tags


def _platform_filter_option_label(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"10008", "walmart"}:
        return "Walmart"
    if normalized == "amazon":
        return "Amazon"
    if normalized == "temu":
        return "TEMU"
    return value


class DailySalesService:
    """Read and shape the daily-sales MART without touching RAW or external APIs."""

    def __init__(self, session: Session) -> None:
        self.repository = DailySalesRepository(session)

    def list_daily_sales(
        self,
        query: DailySalesQuery,
        account_refs: frozenset[str],
    ) -> tuple[DailySalesListData, int, object | None]:
        rows, total, latest_calculated_at = self.repository.list_daily_sales(
            account_refs=account_refs,
            start_date=query.start_date,
            end_date=query.end_date,
            platform=query.platform,
            store_id=query.store_id,
            owner_ref=query.owner_ref,
            search_field=query.search_field,
            keyword=query.keyword,
            batch_values=query.batch_values,
            page=query.page,
            page_size=query.page_size,
        )
        inventory_snapshots = self.repository.daily_sales_inventory_snapshot_map(rows)

        (
            sales_qty,
            order_count,
            sales_amount,
            sales_currency,
            order_profit_amount,
            order_profit_currency,
            ad_spend_amount,
            sem_ad_spend_amount,
            ad_spend_currency,
            wfs_available_quantity,
        ) = self.repository.daily_sales_summary(
            account_refs=account_refs,
            start_date=query.start_date,
            end_date=query.end_date,
            platform=query.platform,
            store_id=query.store_id,
            owner_ref=query.owner_ref,
            search_field=query.search_field,
            keyword=query.keyword,
            batch_values=query.batch_values,
        )

        (
            refund_qty,
            refund_amount,
            refund_loss_amount,
            refund_currency,
        ) = self.repository.refund_event_summary(
            account_refs=account_refs,
            start_date=query.start_date,
            end_date=query.end_date,
            platform=query.platform,
            store_id=query.store_id,
            owner_ref=query.owner_ref,
            search_field=query.search_field,
            keyword=query.keyword,
            batch_values=query.batch_values,
        )
        return (
            DailySalesListData(
                items=[
                    self._to_read(
                        row,
                        inventory_snapshots.get(
                            (
                                row.business_date_la,
                                row.source_account_ref,
                                row.store_id,
                                row.item_id,
                            )
                        ),
                    )
                    for row in rows
                ],
                summary=DailySalesSummaryRead(
                    sales_qty=_decimal(sales_qty),
                    order_count=_decimal(order_count),
                    sales_amount=_decimal(sales_amount),
                    sales_currency_code=sales_currency or "USD",
                    order_profit_amount=_decimal(order_profit_amount),
                    order_profit_currency_code=order_profit_currency or "USD",
                    ad_spend_amount=_decimal(ad_spend_amount),
                    sem_ad_spend_amount=_decimal(sem_ad_spend_amount),
                    total_ad_spend_amount=_decimal(ad_spend_amount) + _decimal(sem_ad_spend_amount),
                    ad_spend_currency_code=ad_spend_currency or "USD",
                    wfs_available_quantity=(
                        None if wfs_available_quantity is None else _decimal(wfs_available_quantity)
                    ),
                    refund_event_qty=_decimal(refund_qty),
                    refund_event_amount=_decimal(refund_amount),
                    refund_loss_amount=_decimal(refund_loss_amount),
                    refund_event_currency_code=refund_currency or "USD",
                ),
            ),
            total,
            latest_calculated_at,
        )

    def filter_options(
        self,
        query: DailySalesQuery,
        account_refs: frozenset[str],
    ) -> DataPageFilterOptionsData:
        rows = self.repository.filter_options(
            account_refs=account_refs,
            start_date=query.start_date,
            end_date=query.end_date,
            platform=query.platform,
            store_id=query.store_id,
            owner_ref=query.owner_ref,
            search_field=query.search_field,
            keyword=query.keyword,
        )

        platform_options: list[DataPageFilterOptionRead] = []
        seen_platforms: set[str] = set()
        for value, _label, count in rows["platforms"]:
            label = _platform_filter_option_label(value)
            option_value = label
            if option_value in seen_platforms:
                continue
            seen_platforms.add(option_value)
            platform_options.append(
                DataPageFilterOptionRead(value=option_value, label=label, count=count)
            )

        return DataPageFilterOptionsData(
            platforms=platform_options,
            owners=[
                DataPageFilterOptionRead(value=value, label=label, count=count)
                for value, label, count in rows["owners"]
            ],
            stores=[
                DataPageFilterOptionRead(value=value, label=label, count=count)
                for value, label, count in rows["stores"]
            ],
        )

    def _to_read(
        self,
        row: DailySalesItemDayMart,
        wfs_available_quantity: object | None,
    ) -> DailySalesItemRead:
        return DailySalesItemRead(
            id=str(row.id),
            business_date_la=row.business_date_la,
            business_timezone=row.business_timezone,
            store_id=row.store_id,
            store_name=row.store_name,
            owner_ref=row.owner_ref,
            item_id=row.item_id,
            msku=row.msku,
            local_sku=row.local_sku,
            local_name=row.local_name,
            title=row.title,
            picture_url=row.picture_url,
            platform_code=row.platform_code,
            gross_sales_qty=_decimal(row.gross_sales_qty),
            gross_order_count=_decimal(row.gross_order_count),
            gross_sales_amount=_decimal(row.gross_sales_amount),
            sample_order_count=_decimal(row.sample_order_count),
            sample_qty=_decimal(row.sample_qty),
            cost_quantity=_decimal(row.cost_quantity),
            sales_qty=_decimal(row.sales_qty),
            order_count=_decimal(row.order_count),
            sales_amount=_decimal(row.sales_amount),
            sales_currency_code=row.sales_currency_code,
            sample_amount=row.sample_amount,
            sales_amount_excluding_sample=row.sales_amount_excluding_sample,
            return_qty=row.return_qty,
            refund_amount=row.refund_amount,
            refund_loss_amount=_refund_loss_amount(row.refund_amount, row.commission_rate),
            refund_currency_code=row.refund_currency_code,
            return_rate_30d=row.return_rate_30d,
            ad_spend_amount=row.ad_spend_amount,
            sem_ad_spend_amount=_decimal(row.sem_ad_spend_amount),
            total_ad_spend_amount=_decimal(row.ad_spend_amount) + _decimal(row.sem_ad_spend_amount),
            ad_spend_currency_code=row.ad_spend_currency_code,
            ad_ratio=row.ad_ratio,
            wfs_available_quantity=wfs_available_quantity,
            wfs_fee_unit_amount=row.wfs_fee_unit_amount,
            wfs_fee_total_amount=row.wfs_fee_total_amount,
            wfs_low_price_surcharge_amount=_decimal(row.wfs_low_price_surcharge_amount),
            wfs_fee_currency_code=row.wfs_fee_currency_code,
            wfs_fee_expected_unit_amount=row.wfs_fee_expected_unit_amount,
            wfs_fee_expected_total_amount=row.wfs_fee_expected_total_amount,
            wfs_fee_actual_total_amount=row.wfs_fee_actual_total_amount,
            wfs_fee_variance_amount=row.wfs_fee_variance_amount,
            wfs_fee_variance_rate=row.wfs_fee_variance_rate,
            wfs_fee_source=row.wfs_fee_source,
            purchase_cost_unit_cny=row.purchase_cost_unit_cny,
            purchase_cost_total_usd=row.purchase_cost_total_usd,
            purchase_cost_estimated_total_usd=row.purchase_cost_estimated_total_usd,
            purchase_cost_actual_total_usd=row.purchase_cost_actual_total_usd,
            purchase_cost_source=row.purchase_cost_source,
            first_leg_cost_unit_cny=row.first_leg_cost_unit_cny,
            first_leg_cost_total_usd=row.first_leg_cost_total_usd,
            first_leg_cost_estimated_total_usd=row.first_leg_cost_estimated_total_usd,
            first_leg_cost_actual_total_usd=row.first_leg_cost_actual_total_usd,
            first_leg_cost_source=row.first_leg_cost_source,
            storage_fee_unit_amount=row.storage_fee_unit_amount,
            storage_fee_total_amount=row.storage_fee_total_amount,
            storage_fee_currency_code=row.storage_fee_currency_code,
            storage_fee_estimated_total_amount=row.storage_fee_estimated_total_amount,
            storage_fee_actual_total_amount=row.storage_fee_actual_total_amount,
            storage_fee_source=row.storage_fee_source,
            exchange_rate=row.exchange_rate,
            fx_date=row.fx_date,
            fx_source=row.fx_source,
            commission_rate=row.commission_rate,
            commission_fee_amount=row.commission_fee_amount,
            commission_fee_currency_code=row.commission_fee_currency_code,
            commission_source=row.commission_source,
            gross_profit_amount=row.gross_profit_amount,
            gross_profit_currency_code=row.gross_profit_currency_code,
            total_cost_amount=(
                None
                if row.gross_profit_amount is None
                else _decimal(row.sales_amount) - _decimal(row.gross_profit_amount)
            ),
            average_profit_per_order=(
                None
                if row.gross_profit_amount is None or not _decimal(row.order_count)
                else (_decimal(row.gross_profit_amount) / _decimal(row.order_count)).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
            ),
            gross_margin=row.gross_margin,
            roi=row.roi,
            cost_status=row.cost_status,
            missing_cost_codes=list(row.missing_cost_codes_json or []),
            calculation_warnings=list(row.calculation_warnings_json or []),
            sales_7d_trend=_trend_points(row.sales_7d_trend_json),
            calc_version=row.calc_version,
            calculated_at=row.calculated_at,
        )


class OrderProfitService:
    """Read and shape the order-profit MART without touching RAW or external APIs."""

    def __init__(self, session: Session) -> None:
        self.repository = OrderProfitRepository(session)
        self.daily_sales_repository = DailySalesRepository(session)

    def list_order_profit(
        self,
        *,
        query: OrderProfitQuery,
        account_refs: frozenset[str],
    ) -> tuple[OrderProfitListData, int, object | None]:
        rows, total, latest_calculated_at = self.repository.list_order_profit(
            account_refs=account_refs,
            start_date=query.start_date,
            end_date=query.end_date,
            store_id=query.store_id,
            search_field=query.search_field,
            keyword=query.keyword,
            page=query.page,
            page_size=query.page_size,
        )

        (
            sales_qty,
            order_count,
            sales_amount,
            sales_currency,
            return_qty,
            refund_amount,
            refund_loss_amount,
            refund_currency,
            order_profit_amount,
            order_profit_currency,
            ad_spend_amount,
            sem_ad_spend_amount,
            ad_spend_currency,
        ) = self.repository.order_profit_summary(
            account_refs=account_refs,
            start_date=query.start_date,
            end_date=query.end_date,
            store_id=query.store_id,
            search_field=query.search_field,
            keyword=query.keyword,
        )

        return (
            OrderProfitListData(
                items=[self._to_read(row) for row in rows],
                summary=OrderProfitSummaryRead(
                    sales_qty=_decimal(sales_qty),
                    order_count=_decimal(order_count),
                    sales_amount=_decimal(sales_amount),
                    sales_currency_code=sales_currency or "USD",
                    return_qty=_decimal(return_qty),
                    refund_amount=_decimal(refund_amount),
                    refund_loss_amount=_decimal(refund_loss_amount),
                    refund_currency_code=refund_currency or "USD",
                    order_profit_amount=_decimal(order_profit_amount),
                    order_profit_currency_code=order_profit_currency or "USD",
                    ad_spend_amount=_decimal(ad_spend_amount),
                    sem_ad_spend_amount=_decimal(sem_ad_spend_amount),
                    total_ad_spend_amount=_decimal(ad_spend_amount) + _decimal(sem_ad_spend_amount),
                    ad_spend_currency_code=ad_spend_currency or "USD",
                    ad_ratio=_percent_ratio(
                        _decimal(ad_spend_amount) + _decimal(sem_ad_spend_amount),
                        _decimal(sales_amount),
                    ),
                ),
            ),
            total,
            latest_calculated_at,
        )

    def order_profit_trend(
        self,
        *,
        query: OrderProfitQuery,
        account_refs: frozenset[str],
    ) -> OrderProfitTrendData:
        rows = self.daily_sales_repository.order_profit_trend(
            account_refs=account_refs,
            start_date=query.start_date,
            end_date=query.end_date,
            platform=query.platform,
            store_id=query.store_id,
            owner_ref=query.owner_ref,
            search_field=query.search_field,
            keyword=query.keyword,
        )

        items: list[OrderProfitTrendPointRead] = []
        for row in rows:
            value = row._mapping
            sales_amount = _decimal(value["sales_amount"])
            order_profit_amount = _decimal(value["order_profit_amount"])
            ad_spend_amount = _decimal(value["ad_spend_amount"])
            sem_ad_spend_amount = _decimal(value["sem_ad_spend_amount"])
            total_ad_spend_amount = _decimal(value["total_ad_spend_amount"])

            items.append(
                OrderProfitTrendPointRead(
                    date=value["date"],
                    sales_qty=_decimal(value["sales_qty"]),
                    order_count=_decimal(value["order_count"]),
                    sales_amount=sales_amount,
                    sales_currency_code=value["sales_currency_code"] or "USD",
                    return_qty=_decimal(value["return_qty"]),
                    refund_amount=_decimal(value["refund_amount"]),
                    refund_loss_amount=_decimal(value["refund_loss_amount"]),
                    refund_currency_code=value["refund_currency_code"] or "USD",
                    order_profit_amount=order_profit_amount,
                    order_profit_currency_code=value["order_profit_currency_code"] or "USD",
                    profit_margin=_percent_ratio(order_profit_amount, sales_amount),
                    ad_spend_amount=ad_spend_amount,
                    sem_ad_spend_amount=sem_ad_spend_amount,
                    total_ad_spend_amount=total_ad_spend_amount,
                    ad_spend_currency_code=value["ad_spend_currency_code"] or "USD",
                    ad_ratio=_percent_ratio(total_ad_spend_amount, sales_amount),
                )
            )

        return OrderProfitTrendData(items=items)

    def _to_read(self, row: OrderProfitSkuDayMart) -> OrderProfitItemRead:
        return OrderProfitItemRead(
            id=str(row.id),
            business_date_la=row.business_date_la,
            business_timezone=row.business_timezone,
            local_sku=row.local_sku,
            item_ids=_string_list(row.item_ids_json),
            store_ids=_string_list(row.store_ids_json),
            store_names=_string_list(getattr(row, "store_names_json", [])),
            owner_refs=_string_list(getattr(row, "owner_refs_json", [])),
            mskus=_string_list(getattr(row, "mskus_json", [])),
            product_name=getattr(row, "product_name", None),
            store_count=row.store_count,
            item_count=row.item_count,
            sales_qty=_decimal(row.sales_qty),
            order_count=_decimal(row.order_count),
            sales_amount=_decimal(row.sales_amount),
            sales_currency_code=row.sales_currency_code,
            sample_qty=_decimal(getattr(row, "sample_qty", None)),
            sample_amount=getattr(row, "sample_amount", None),
            return_qty=_decimal(row.return_qty),
            refund_amount=row.refund_amount,
            refund_loss_amount=_decimal(row.refund_loss_amount),
            return_rate_30d=getattr(row, "return_rate_30d", None),
            ad_spend_amount=row.ad_spend_amount,
            sem_ad_spend_amount=_decimal(row.sem_ad_spend_amount),
            total_ad_spend_amount=_decimal(row.ad_spend_amount) + _decimal(row.sem_ad_spend_amount),
            ad_ratio=_percent_ratio(
                _decimal(row.ad_spend_amount) + _decimal(row.sem_ad_spend_amount),
                _decimal(row.sales_amount),
            ),
            wfs_available_quantity=getattr(row, "wfs_available_quantity", None),
            wfs_fee_unit_amount=getattr(row, "wfs_fee_unit_amount", None),
            commission_fee_amount=row.commission_fee_amount,
            wfs_fee_total_amount=row.wfs_fee_total_amount,
            wfs_low_price_surcharge_amount=_decimal(row.wfs_low_price_surcharge_amount),
            purchase_cost_unit_cny=getattr(row, "purchase_cost_unit_cny", None),
            purchase_cost_total_usd=row.purchase_cost_total_usd,
            first_leg_cost_unit_cny=getattr(row, "first_leg_cost_unit_cny", None),
            first_leg_cost_total_usd=row.first_leg_cost_total_usd,
            storage_fee_unit_amount=getattr(row, "storage_fee_unit_amount", None),
            storage_fee_total_amount=row.storage_fee_total_amount,
            gross_profit_amount=row.gross_profit_amount,
            gross_profit_currency_code=row.gross_profit_currency_code,
            total_cost_amount=getattr(row, "total_cost_amount", None),
            average_profit_per_order=getattr(row, "average_profit_per_order", None),
            gross_margin=row.gross_margin,
            roi=row.roi,
            cost_status=row.cost_status,
            missing_cost_codes=list(row.missing_cost_codes_json or []),
            calc_version=row.calc_version,
            calculated_at=row.calculated_at,
        )


class ListingManagementService:
    """Read and shape the listing-management MART without touching RAW or external APIs."""

    def __init__(self, session: Session) -> None:
        self.repository = ListingManagementRepository(session)
        self.tag_repository = ListingTagRepository(session)

    @staticmethod
    def _listing_archive_status_values(raw: str | None) -> set[str]:
        return {value.strip() for value in (raw or "").split(",") if value.strip()}

    def list_listings(
        self,
        query: ListingManagementQuery,
        account_refs: frozenset[str],
    ) -> tuple[ListingManagementListData, int, object | None]:
        rows, total, latest_calculated_at = self.repository.list_listings(
            account_refs=account_refs,
            store_id=query.store_id,
            owner_ref=query.owner_ref,
            product_type=query.product_type,
            status=query.status,
            tag=query.tag,
            archive_status=query.archive_status,
            summary_filter=query.summary_filter,
            search_field=query.search_field,
            keyword=query.keyword,
            batch_values=query.batch_values,
            page=query.page,
            page_size=query.page_size,
        )
        custom_tags = self.tag_repository.tags_for_listing_rows(rows)
        archive_states = self.repository.archive_states_for_listing_rows(rows)
        archive_states = self._normalize_listing_archive_state_keys(archive_states)
        return (
            ListingManagementListData(
                items=[
                    self._to_read(
                        row,
                        custom_tags.get((str(row.source_account_ref), str(row.item_id))),
                        bool(
                            archive_states.get(str(row.id))
                            and archive_states[str(row.id)].is_archived
                        ),
                        archive_reason=getattr(
                            archive_states.get(str(row.id)),
                            "archive_reason",
                            None,
                        ),
                    )
                    for row in rows
                ],
            ),
            total,
            latest_calculated_at,
        )

    def listing_summary(
        self,
        query: ListingManagementQuery,
        account_refs: frozenset[str],
    ) -> ListingManagementSummaryData:
        (
            total,
            online,
            buybox_exception,
            rating_warning,
            resold_warning,
            strike_price_exception,
        ) = self.repository.listing_summary(
            account_refs=account_refs,
            store_id=query.store_id,
            owner_ref=query.owner_ref,
            product_type=query.product_type,
            status=query.status,
            tag=query.tag,
            archive_status=query.archive_status,
            search_field=query.search_field,
            keyword=query.keyword,
            batch_values=query.batch_values,
        )

        return ListingManagementSummaryData(
            total=total,
            online=online,
            buybox_exception=buybox_exception,
            rating_warning=rating_warning,
            resold_warning=resold_warning,
            strike_price_exception=strike_price_exception,
        )

    def listing_filter_options(
        self,
        account_refs: frozenset[str],
    ) -> ListingManagementFilterOptionsData:
        rows = self.repository.listing_filter_options(account_refs=account_refs)

        tag_rows = {value: (value, label, count) for value, label, count in rows["tags"]}
        db_tag_rows = {
            tag.name: (tag.name, tag.name, usage)
            for tag, usage in self.tag_repository.list_tags(account_refs=account_refs)
        }
        tag_rows.update(db_tag_rows)

        return ListingManagementFilterOptionsData(
            stores=[
                DataPageFilterOptionRead(value=value, label=label, count=count)
                for value, label, count in rows["stores"]
            ],
            owners=[
                DataPageFilterOptionRead(value=value, label=label, count=count)
                for value, label, count in rows["owners"]
            ],
            product_types=[
                DataPageFilterOptionRead(value=value, label=label, count=count)
                for value, label, count in rows["product_types"]
            ],
            tags=[
                DataPageFilterOptionRead(value=value, label=label, count=count)
                for value, label, count in sorted(
                    tag_rows.values(),
                    key=lambda item: item[1],
                )
            ],
            archive_statuses=self.repository.archive_status_filter_options(account_refs),
        )

    def export_listing_csv(
        self,
        query: ListingManagementQuery,
        account_refs: frozenset[str],
    ) -> str:
        rows = self.repository.export_listings(
            account_refs=account_refs,
            store_id=query.store_id,
            owner_ref=query.owner_ref,
            product_type=query.product_type,
            status=query.status,
            tag=query.tag,
            archive_status=query.archive_status,
            summary_filter=query.summary_filter,
            search_field=query.search_field,
            keyword=query.keyword,
            batch_values=query.batch_values,
            max_rows=10000,
        )
        custom_tags = self.tag_repository.tags_for_listing_rows(rows)

        output = StringIO()
        writer = csv.writer(output)

        writer.writerow(
            [
                "店铺",
                "商品ID",
                "SKU",
                "MSKU",
                "品名",
                "标题",
                "负责人",
                "开发人",
                "商品等级",
                "自定义标签",
                "划线价",
                "售价",
                "Listing状态",
                "生命周期",
                "发货方式",
                "购物车状态",
                "Walmart卖家",
                "是否跟卖",
                "评分",
                "评论数",
                "WFS可售库存",
                "可售库存",
                "在途库存",
                "近7天销量",
                "近14天销量",
                "近30天销量",
                "近30天广告费",
                "类目",
                "品牌",
                "停用原因",
                "GTIN",
                "UPC",
                "上架时间",
                "检查时间",
            ]
        )

        for row in rows:
            item = self._to_read(
                row,
                custom_tags.get((str(row.source_account_ref), str(row.item_id))),
            )

            writer.writerow(
                [
                    self._csv_value(item.store_name or item.store_id),
                    self._csv_value(item.item_id),
                    self._csv_value(item.local_sku),
                    self._csv_value(item.msku),
                    self._csv_value(item.local_name),
                    self._csv_value(item.title),
                    self._csv_value(item.owner_name or item.owner_ref),
                    self._csv_value(item.product_developer_name),
                    self._csv_value(item.product_grade),
                    self._csv_value(item.tags),
                    self._csv_value(item.strike_price_amount),
                    self._csv_value(item.sale_price_amount),
                    self._csv_value(item.listing_status),
                    self._csv_value(item.lifecycle_status),
                    self._csv_value(item.fulfillment_type_name or item.fulfillment_type),
                    self._csv_value(item.buybox_status),
                    self._csv_value(item.walmart_seller),
                    self._csv_value("是" if item.is_hijacked else "否"),
                    self._csv_value(item.average_rating),
                    self._csv_value(item.review_count),
                    self._csv_value(item.wfs_available_quantity),
                    self._csv_value(item.available_quantity),
                    self._csv_value(item.inbound_quantity),
                    self._csv_value(item.sales_7d),
                    self._csv_value(item.sales_14d),
                    self._csv_value(item.sales_30d),
                    self._csv_value(item.ad_spend_30d_amount),
                    self._csv_value(item.category),
                    self._csv_value(item.brand),
                    self._csv_value(item.disabled_reason),
                    self._csv_value(item.gtin),
                    self._csv_value(item.upc),
                    self._csv_value(item.listing_start_at_utc),
                    self._csv_value(item.calculated_at),
                ]
            )

        return output.getvalue()

    @staticmethod
    def _csv_value(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return "、".join(str(item) for item in value if item is not None)
        return str(value)

    @staticmethod
    def _normalize_listing_archive_state_keys(archive_states):
        if not hasattr(archive_states, "items"):
            return archive_states

        from uuid import UUID

        normalized = {}
        for key, value in archive_states.items():
            normalized[key] = value
            normalized[str(key)] = value
            try:
                normalized[UUID(str(key))] = value
            except (TypeError, ValueError):
                pass

        return normalized

    def archive_listing(
        self,
        *,
        listing_id: str,
        account_refs: frozenset[str],
        actor_ref: str,
        reason: str,
    ) -> ListingArchiveActionData:
        listing = self.repository.get_listing_by_id(
            listing_id=listing_id,
            account_refs=account_refs,
        )
        if listing is None:
            raise ValueError("Listing 不存在或无权访问")

        archive_reason = reason.strip()
        if len(archive_reason) < 2:
            raise ValueError("归档原因至少需要 2 个字")
        state = self.repository.set_listing_archive_state(
            listing=listing,
            archived=True,
            actor_ref=actor_ref,
            archive_reason=archive_reason,
        )
        self.repository.session.commit()
        return self._to_archive_action_data(str(listing.id), state)

    def restore_listing(
        self,
        *,
        listing_id: str,
        account_refs: frozenset[str],
        actor_ref: str,
    ) -> ListingArchiveActionData:
        listing = self.repository.get_listing_by_id(
            listing_id=listing_id,
            account_refs=account_refs,
        )
        if listing is None:
            raise ValueError("Listing 不存在或无权访问")
        state = self.repository.set_listing_archive_state(
            listing=listing,
            archived=False,
            actor_ref=actor_ref,
        )
        self.repository.session.commit()
        return self._to_archive_action_data(str(listing.id), state)

    @staticmethod
    def _to_archive_action_data(
        listing_id: str,
        state: object,
    ) -> ListingArchiveActionData:
        return ListingArchiveActionData(
            listing_id=listing_id,
            is_archived=bool(state.is_archived),
            archive_reason=getattr(state, "archive_reason", None),
            archived_at=getattr(state, "archived_at", None),
            archived_by=getattr(state, "archived_by", None),
            restored_at=getattr(state, "restored_at", None),
            restored_by=getattr(state, "restored_by", None),
        )

    def get_gpt_analysis_link(
        self,
        *,
        listing_id: str,
        account_refs: frozenset[str],
    ) -> ListingGptAnalysisLinkRead:
        listing = self.repository.get_listing_by_id(
            listing_id=listing_id,
            account_refs=account_refs,
        )
        if listing is None:
            raise ValueError("Listing 不存在或无权访问")
        link = self.repository.get_gpt_analysis_link(listing_id=listing.id)
        return self._to_gpt_analysis_link_read(str(listing.id), link)

    def update_gpt_analysis_link(
        self,
        *,
        listing_id: str,
        payload: ListingGptAnalysisLinkUpdateRequest,
        account_refs: frozenset[str],
        actor_ref: str,
    ) -> ListingGptAnalysisLinkRead:
        listing = self.repository.get_listing_by_id(
            listing_id=listing_id,
            account_refs=account_refs,
        )
        if listing is None:
            raise ValueError("Listing 不存在或无权访问")
        link = self.repository.upsert_gpt_analysis_link(
            listing=listing,
            keyword_analysis_url=payload.keyword_analysis_url,
            ad_analysis_url=payload.ad_analysis_url,
            actor_ref=actor_ref,
        )
        self.repository.session.commit()
        return self._to_gpt_analysis_link_read(str(listing.id), link)

    @staticmethod
    def _to_gpt_analysis_link_read(
        listing_id: str,
        link: object | None,
    ) -> ListingGptAnalysisLinkRead:
        if link is None:
            return ListingGptAnalysisLinkRead(listing_id=listing_id)
        return ListingGptAnalysisLinkRead(
            listing_id=listing_id,
            keyword_analysis_url=str(link.keyword_analysis_url or ""),
            ad_analysis_url=str(link.ad_analysis_url or ""),
            updated_by=getattr(link, "updated_by", None),
            updated_at=getattr(link, "updated_at", None),
        )

    def list_tags(self, account_refs: frozenset[str]) -> ListingTagListData:
        return ListingTagListData(
            items=[
                self._to_tag_read(tag, usage)
                for tag, usage in self.tag_repository.list_tags(account_refs=account_refs)
            ],
        )

    def create_tag(self, payload: ListingTagCreateRequest) -> ListingTagRead:
        tag = self.tag_repository.create_tag(
            name=payload.name,
            color=payload.color,
            sort_order=payload.sort_order,
        )
        return self._to_tag_read(tag, 0)

    def update_tag(self, tag_id: str, payload: ListingTagUpdateRequest) -> ListingTagRead:
        tag = self.tag_repository.update_tag(
            tag_id=tag_id,
            name=payload.name,
            color=payload.color,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        return self._to_tag_read(tag, 0)

    def delete_tag(self, tag_id: str) -> None:
        self.tag_repository.delete_tag(tag_id=tag_id)

    def batch_set_tags(
        self,
        *,
        payload: ListingTagBatchSetRequest,
        account_refs: frozenset[str],
    ) -> ListingTagBatchSetData:
        updated, tag_count = self.tag_repository.batch_set_tags(
            account_refs=account_refs,
            listing_ids=list(payload.listing_ids),
            tag_ids=list(payload.tag_ids),
            tag_values=list(payload.tag_values),
            mode=payload.mode,
        )
        return ListingTagBatchSetData(
            updated_listings=updated,
            tag_count=tag_count,
            mode=payload.mode,
        )

    def _to_tag_read(self, tag: object, usage: int) -> ListingTagRead:
        return ListingTagRead(
            id=str(tag.id),
            name=str(tag.name),
            color=str(tag.color),
            usage=usage,
            sort_order=int(tag.sort_order or 0),
            is_active=bool(tag.is_active),
        )

    def _to_read(
        self,
        row: ListingManagementCurrentMart,
        custom_tags: list[str] | None = None,
        is_archived: bool = False,
        archive_reason: str | None = None,
    ) -> ListingManagementItemRead:
        return ListingManagementItemRead(
            id=str(row.id),
            source_account_ref=row.source_account_ref,
            platform_code=row.platform_code,
            store_id=row.store_id,
            store_name=row.store_name,
            item_id=row.item_id,
            msku=row.msku,
            local_sku=row.local_sku,
            local_name=row.local_name,
            title=row.title,
            picture_url=row.picture_url,
            item_url=row.item_url,
            owner_ref=row.owner_ref,
            owner_uid=getattr(row, "owner_uid", None),
            owner_name=getattr(row, "owner_name", None),
            product_developer_uid=getattr(row, "product_developer_uid", None),
            product_developer_name=getattr(row, "product_developer_name", None),
            product_grade=row.product_grade,
            tags=custom_tags if custom_tags is not None else _tag_list(row.tags_json),
            strike_price_amount=row.strike_price_amount,
            strike_price_currency_code=row.strike_price_currency_code,
            sale_price_amount=row.sale_price_amount,
            sale_price_currency_code=row.sale_price_currency_code,
            listing_status=row.listing_status,
            lifecycle_status=row.lifecycle_status,
            fulfillment_type=getattr(row, "fulfillment_type", None),
            fulfillment_type_name=getattr(row, "fulfillment_type_name", None),
            listing_start_at_utc=row.listing_start_at_utc,
            listing_start_source_raw=getattr(row, "listing_start_source_raw", None),
            category=row.category,
            wfs_available_quantity=row.wfs_available_quantity,
            available_quantity=row.available_quantity,
            inbound_quantity=row.inbound_quantity,
            sales_7d=_decimal(row.sales_7d),
            sales_14d=_decimal(row.sales_14d),
            sales_30d=_decimal(row.sales_30d),
            ad_spend_30d_amount=row.ad_spend_30d_amount,
            ad_spend_currency_code=row.ad_spend_currency_code,
            buybox_status=row.buybox_status,
            walmart_seller=row.walmart_seller,
            is_hijacked=row.is_hijacked,
            average_rating=row.average_rating,
            review_count=row.review_count,
            brand=row.brand,
            disabled_reason=row.disabled_reason,
            wfs_fee_amount=row.wfs_fee_amount,
            wfs_fee_currency_code=row.wfs_fee_currency_code,
            gtin=row.gtin,
            upc=row.upc,
            calculated_at=row.calculated_at,
            is_archived=is_archived,
            archive_reason=archive_reason,
        )
