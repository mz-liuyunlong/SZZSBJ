from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.ads_search_terms.models import (
    AdsSearchTermAction,
    AdsSearchTermActionEvent,
    WalmartAdSearchTermDailyFact,
    WalmartManualKeywordDailyFact,
)
from app.modules.ads_search_terms.schemas import (
    ActionCreate,
    ActionListData,
    ActionRead,
    SearchTermAggregateListData,
    SearchTermListData,
    SearchTermQuery,
    SearchTermAggregateRead,
    SearchTermRead,
    SearchTermSummaryData,
    SearchTermTrendData,
    SearchTermTrendPoint,
)


def normalize_term(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _scope(query: SearchTermQuery, accounts: frozenset[str]):
    if query.end_date < query.start_date or (query.end_date - query.start_date).days > 92:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)

    statement = select(WalmartAdSearchTermDailyFact).where(
        WalmartAdSearchTermDailyFact.source_account_ref.in_(accounts),
        WalmartAdSearchTermDailyFact.business_date_la.between(query.start_date, query.end_date),
        WalmartAdSearchTermDailyFact.attribution_days == 14,
    )
    if query.store_ids:
        statement = statement.where(WalmartAdSearchTermDailyFact.store_id.in_(query.store_ids))
    if query.advertiser_ids:
        statement = statement.where(
            WalmartAdSearchTermDailyFact.advertiser_id.in_(query.advertiser_ids)
        )
    if query.campaign_ids:
        statement = statement.where(
            WalmartAdSearchTermDailyFact.campaign_id.in_(query.campaign_ids)
        )
    if query.targeting_type != "all":
        statement = statement.where(
            WalmartAdSearchTermDailyFact.targeting_type == query.targeting_type
        )
    if query.query:
        statement = statement.where(
            WalmartAdSearchTermDailyFact.searched_keyword.ilike(f"%{query.query}%")
        )
    if query.conversion_state == "orders":
        statement = statement.where(WalmartAdSearchTermDailyFact.attributed_orders > 0)
    if query.conversion_state == "no_orders":
        statement = statement.where(WalmartAdSearchTermDailyFact.attributed_orders == 0)
    return statement


class AdsSearchTermsService:
    def __init__(self, session: Session):
        self.session = session

    def list_terms(
        self,
        query: SearchTermQuery,
        accounts: frozenset[str],
    ) -> SearchTermListData:
        statement = _scope(query, accounts)
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        rows = self.session.scalars(
            statement.order_by(
                WalmartAdSearchTermDailyFact.attributed_orders.desc().nullslast(),
                WalmartAdSearchTermDailyFact.ad_spend_amount.desc().nullslast(),
                WalmartAdSearchTermDailyFact.searched_keyword,
            )
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        ).all()
        return SearchTermListData(
            items=[SearchTermRead.model_validate(row) for row in rows],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )


    def list_aggregates(
        self,
        query: SearchTermQuery,
        accounts: frozenset[str],
    ) -> SearchTermAggregateListData:
        subquery = _scope(query, accounts).subquery()
        manual_same_store = (
            select(WalmartManualKeywordDailyFact.id)
            .where(
                WalmartManualKeywordDailyFact.source_account_ref
                == subquery.c.source_account_ref,
                WalmartManualKeywordDailyFact.store_id == subquery.c.store_id,
                WalmartManualKeywordDailyFact.normalized_keyword
                == subquery.c.normalized_search_term,
                WalmartManualKeywordDailyFact.attribution_days == 14,
            )
            .exists()
        )
        manual_other_store = (
            select(WalmartManualKeywordDailyFact.id)
            .where(
                WalmartManualKeywordDailyFact.source_account_ref
                == subquery.c.source_account_ref,
                WalmartManualKeywordDailyFact.store_id
                != subquery.c.store_id,
                WalmartManualKeywordDailyFact.normalized_keyword
                == subquery.c.normalized_search_term,
                WalmartManualKeywordDailyFact.attribution_days == 14,
            )
            .exists()
        )
        grouped = (
            select(
                subquery.c.normalized_search_term,
                func.min(subquery.c.searched_keyword),
                func.bool_or(subquery.c.targeting_type == "auto"),
                func.bool_or(subquery.c.targeting_type == "manual"),
                func.count(func.distinct(subquery.c.store_id)),
                func.count(
                    func.distinct(
                        func.concat(
                            subquery.c.source_account_ref,
                            ":",
                            func.coalesce(subquery.c.store_id, ""),
                            ":",
                            func.coalesce(subquery.c.item_id, ""),
                        )
                    )
                ).filter(subquery.c.item_id.is_not(None)),
                func.count(func.distinct(subquery.c.campaign_id)),
                func.coalesce(func.sum(subquery.c.num_ads_shown), 0),
                func.coalesce(func.sum(subquery.c.num_ads_clicks), 0),
                func.coalesce(func.sum(subquery.c.ad_spend_amount), 0),
                func.coalesce(func.sum(subquery.c.attributed_orders), 0),
                func.coalesce(func.sum(subquery.c.advertised_sku_sales_amount), 0),
                func.coalesce(func.sum(subquery.c.other_sku_sales_amount), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (subquery.c.targeting_type == "auto", subquery.c.attributed_orders),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (subquery.c.targeting_type == "manual", subquery.c.attributed_orders),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.bool_or(manual_same_store),
                func.bool_or(manual_other_store),
                func.max(subquery.c.synced_at),
            )
            .group_by(subquery.c.normalized_search_term)
        )
        total = int(
            self.session.scalar(
                select(func.count()).select_from(
                    select(subquery.c.normalized_search_term)
                    .group_by(subquery.c.normalized_search_term)
                    .subquery()
                )
            )
            or 0
        )
        rows = self.session.execute(
            grouped.order_by(
                func.sum(subquery.c.attributed_orders).desc(),
                func.sum(subquery.c.ad_spend_amount).desc(),
                subquery.c.normalized_search_term,
            )
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        ).all()
        return SearchTermAggregateListData(
            items=[
                SearchTermAggregateRead(
                    normalized_search_term=row[0],
                    searched_keyword=row[1],
                    has_auto=bool(row[2]),
                    has_manual=bool(row[3]),
                    store_count=int(row[4] or 0),
                    listing_count=int(row[5] or 0),
                    campaign_count=int(row[6] or 0),
                    impressions=int(row[7] or 0),
                    clicks=int(row[8] or 0),
                    spend=Decimal(row[9] or 0),
                    orders=Decimal(row[10] or 0),
                    direct_sales=Decimal(row[11] or 0),
                    other_sales=Decimal(row[12] or 0),
                    auto_orders=Decimal(row[13] or 0),
                    manual_orders=Decimal(row[14] or 0),
                    manual_covered_same_store=bool(row[15]),
                    manual_covered_other_store=bool(row[16]),
                    freshness_at=row[17],
                )
                for row in rows
            ],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    def summary(
        self,
        query: SearchTermQuery,
        accounts: frozenset[str],
    ) -> SearchTermSummaryData:
        subquery = _scope(query, accounts).subquery()
        manual_keyword_exists = (
            select(WalmartManualKeywordDailyFact.id)
            .where(
                WalmartManualKeywordDailyFact.source_account_ref == subquery.c.source_account_ref,
                WalmartManualKeywordDailyFact.advertiser_id == subquery.c.advertiser_id,
                WalmartManualKeywordDailyFact.normalized_keyword
                == subquery.c.normalized_search_term,
                WalmartManualKeywordDailyFact.attribution_days == 14,
            )
            .exists()
        )
        values = self.session.execute(
            select(
                func.count(func.distinct(subquery.c.normalized_search_term)),
                func.count(func.distinct(subquery.c.normalized_search_term)).filter(
                    subquery.c.attributed_orders > 0
                ),
                func.count().filter(
                    and_(
                        subquery.c.targeting_type == "auto",
                        subquery.c.attributed_orders > 0,
                        ~manual_keyword_exists,
                    )
                ),
                func.count().filter(
                    and_(
                        subquery.c.attributed_orders == 0,
                        subquery.c.ad_spend_amount > 0,
                    )
                ),
                func.coalesce(func.sum(subquery.c.ad_spend_amount), 0),
                func.coalesce(func.sum(subquery.c.attributed_orders), 0),
                func.coalesce(func.sum(subquery.c.advertised_sku_sales_amount), 0),
                func.coalesce(func.sum(subquery.c.other_sku_sales_amount), 0),
                func.max(subquery.c.synced_at),
                func.count().filter(subquery.c.listing_mapping_status != "unique"),
            )
        ).one()
        return SearchTermSummaryData(
            total_terms=values[0] or 0,
            converting_terms=values[1] or 0,
            auto_converting_not_manually_covered=values[2] or 0,
            no_order_terms_with_spend=values[3] or 0,
            ad_spend_total=Decimal(values[4] or 0),
            attributed_orders_total=Decimal(values[5] or 0),
            direct_sales_total=Decimal(values[6] or 0),
            other_sales_total=Decimal(values[7] or 0),
            freshness_at=values[8],
            mapping_unresolved_count=values[9] or 0,
        )

    def trends(
        self,
        term: str,
        start: date,
        end: date,
        accounts: frozenset[str],
    ) -> SearchTermTrendData:
        if end < start or (end - start).days > 92:
            raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
        rows = self.session.execute(
            select(
                WalmartAdSearchTermDailyFact.business_date_la,
                func.sum(WalmartAdSearchTermDailyFact.num_ads_shown),
                func.sum(WalmartAdSearchTermDailyFact.num_ads_clicks),
                func.sum(WalmartAdSearchTermDailyFact.ad_spend_amount),
                func.sum(WalmartAdSearchTermDailyFact.attributed_orders),
                func.sum(WalmartAdSearchTermDailyFact.advertised_sku_sales_amount),
                func.sum(WalmartAdSearchTermDailyFact.other_sku_sales_amount),
            )
            .where(
                WalmartAdSearchTermDailyFact.source_account_ref.in_(accounts),
                WalmartAdSearchTermDailyFact.normalized_search_term == normalize_term(term),
                WalmartAdSearchTermDailyFact.business_date_la.between(start, end),
                WalmartAdSearchTermDailyFact.attribution_days == 14,
            )
            .group_by(WalmartAdSearchTermDailyFact.business_date_la)
            .order_by(WalmartAdSearchTermDailyFact.business_date_la)
        ).all()
        return SearchTermTrendData(
            items=[
                SearchTermTrendPoint(
                    business_date_la=row[0],
                    impressions=int(row[1] or 0),
                    clicks=int(row[2] or 0),
                    spend=Decimal(row[3] or 0),
                    orders=Decimal(row[4] or 0),
                    direct_sales=Decimal(row[5] or 0),
                    other_sales=Decimal(row[6] or 0),
                )
                for row in rows
            ]
        )

    def create_action(
        self,
        payload: ActionCreate,
        actor: str,
        accounts: frozenset[str],
    ) -> ActionRead:
        if payload.source_account_ref not in accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        if payload.source_fact_id is not None:
            fact = self.session.get(WalmartAdSearchTermDailyFact, payload.source_fact_id)
            if (
                fact is None
                or fact.source_account_ref != payload.source_account_ref
                or fact.source_account_ref not in accounts
            ):
                raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)

        now = datetime.now(timezone.utc)
        term = payload.search_term.strip()
        action = AdsSearchTermAction(
            id=uuid4(),
            source_account_ref=payload.source_account_ref,
            source_fact_id=payload.source_fact_id,
            action_type=payload.action_type,
            search_term=term,
            normalized_search_term=normalize_term(term),
            target_scope_json=payload.target_scope,
            status="pending_manual",
            effect_status="pending",
            reason=payload.reason,
            created_by=actor,
            created_at=now,
            updated_at=now,
        )
        self.session.add(action)
        self.session.flush()
        self.session.add(
            AdsSearchTermActionEvent(
                id=uuid4(),
                action_id=action.id,
                event_type="created",
                actor_ref=actor,
                detail_json={"provider_write": "not_performed"},
                created_at=now,
            )
        )
        self.session.commit()
        self.session.refresh(action)
        return ActionRead.model_validate(action)

    def list_actions(
        self,
        accounts: frozenset[str],
        page: int,
        page_size: int,
    ) -> ActionListData:
        statement = select(AdsSearchTermAction).where(
            AdsSearchTermAction.source_account_ref.in_(accounts)
        )
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        rows = self.session.scalars(
            statement.order_by(AdsSearchTermAction.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return ActionListData(
            items=[ActionRead.model_validate(row) for row in rows],
            total=total,
        )

    def complete_action(
        self,
        action_id: UUID,
        note: str,
        actor: str,
        accounts: frozenset[str],
    ) -> ActionRead:
        action = self.session.scalar(
            select(AdsSearchTermAction)
            .where(
                AdsSearchTermAction.id == action_id,
                AdsSearchTermAction.source_account_ref.in_(accounts),
            )
            .with_for_update()
        )
        if action is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        if action.status != "pending_manual":
            raise ApiError(
                code="ADS_SEARCH_TERM_ACTION_NOT_PENDING",
                status_code=409,
            )

        now = datetime.now(timezone.utc)
        action.status = "manually_completed"
        action.completed_by = actor
        action.completion_note = note
        action.completed_at = now
        action.updated_at = now
        self.session.add(
            AdsSearchTermActionEvent(
                id=uuid4(),
                action_id=action.id,
                event_type="manual_completion",
                actor_ref=actor,
                detail_json={"provider_write": "not_performed"},
                created_at=now,
            )
        )
        self.session.commit()
        self.session.refresh(action)
        return ActionRead.model_validate(action)
