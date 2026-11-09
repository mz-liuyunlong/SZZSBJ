from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from app.core.api import ApiError, ErrorCode
from app.modules.ads_search_terms.models import AdsSearchTermAction, AdsSearchTermActionEvent, WalmartAdSearchTermDailyFact, WalmartManualKeywordDailyFact
from app.modules.ads_search_terms.schemas import ActionComplete, ActionCreate, ActionListData, ActionRead, SearchTermListData, SearchTermQuery, SearchTermRead, SearchTermSummaryData, SearchTermTrendData, SearchTermTrendPoint

def normalize_term(value: str) -> str:
    return " ".join(value.strip().casefold().split())

def _scope(query: SearchTermQuery, accounts: frozenset[str]):
    if query.end_date < query.start_date or (query.end_date-query.start_date).days > 92:
        raise ApiError(code=ErrorCode.VALIDATION_ERROR, status_code=422)
    stmt=select(WalmartAdSearchTermDailyFact).where(
        WalmartAdSearchTermDailyFact.source_account_ref.in_(accounts),
        WalmartAdSearchTermDailyFact.business_date_la.between(query.start_date,query.end_date))
    if query.store_ids: stmt=stmt.where(WalmartAdSearchTermDailyFact.store_id.in_(query.store_ids))
    if query.advertiser_ids: stmt=stmt.where(WalmartAdSearchTermDailyFact.advertiser_id.in_(query.advertiser_ids))
    if query.campaign_ids: stmt=stmt.where(WalmartAdSearchTermDailyFact.campaign_id.in_(query.campaign_ids))
    if query.targeting_type!="all": stmt=stmt.where(WalmartAdSearchTermDailyFact.targeting_type==query.targeting_type)
    if query.query: stmt=stmt.where(WalmartAdSearchTermDailyFact.searched_keyword.ilike(f"%{query.query}%"))
    if query.conversion_state=="orders": stmt=stmt.where(WalmartAdSearchTermDailyFact.attributed_orders>0)
    if query.conversion_state=="no_orders": stmt=stmt.where(WalmartAdSearchTermDailyFact.attributed_orders==0)
    return stmt

class AdsSearchTermsService:
    def __init__(self, session: Session): self.session=session
    def list_terms(self,q: SearchTermQuery,accounts:frozenset[str])->SearchTermListData:
        stmt=_scope(q,accounts)
        total=int(self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows=self.session.scalars(stmt.order_by(WalmartAdSearchTermDailyFact.attributed_orders.desc().nullslast(),WalmartAdSearchTermDailyFact.ad_spend_amount.desc().nullslast(),WalmartAdSearchTermDailyFact.searched_keyword).offset((q.page-1)*q.page_size).limit(q.page_size)).all()
        return SearchTermListData(items=[SearchTermRead.model_validate(x) for x in rows],total=total,page=q.page,page_size=q.page_size)
    def summary(self,q:SearchTermQuery,accounts:frozenset[str])->SearchTermSummaryData:
        sub=_scope(q,accounts).subquery()
        # Scalar aggregates are calculated over the full filtered result, not the current page.
        cols=self.session.execute(select(
            func.count(func.distinct(sub.c.normalized_search_term)),
            func.count(func.distinct(sub.c.normalized_search_term)).filter(sub.c.attributed_orders>0),
            func.count().filter(and_(sub.c.targeting_type=="auto",sub.c.attributed_orders>0,~select(WalmartManualKeywordDailyFact.id).where(WalmartManualKeywordDailyFact.source_account_ref==sub.c.source_account_ref,WalmartManualKeywordDailyFact.advertiser_id==sub.c.advertiser_id,WalmartManualKeywordDailyFact.normalized_keyword==sub.c.normalized_search_term).exists())),
            func.count().filter(and_(sub.c.attributed_orders==0,sub.c.ad_spend_amount>0)),
            func.coalesce(func.sum(sub.c.ad_spend_amount),0),func.coalesce(func.sum(sub.c.attributed_orders),0),
            func.coalesce(func.sum(sub.c.advertised_sku_sales_amount),0),func.coalesce(func.sum(sub.c.other_sku_sales_amount),0),
            func.max(sub.c.synced_at),func.count().filter(sub.c.listing_mapping_status!="unique")
        )).one()
        return SearchTermSummaryData(total_terms=cols[0] or 0,converting_terms=cols[1] or 0,auto_converting_not_manually_covered=cols[2] or 0,no_order_terms_with_spend=cols[3] or 0,ad_spend_total=Decimal(cols[4] or 0),attributed_orders_total=Decimal(cols[5] or 0),direct_sales_total=Decimal(cols[6] or 0),other_sales_total=Decimal(cols[7] or 0),freshness_at=cols[8],mapping_unresolved_count=cols[9] or 0)
    def trends(self,term:str,start:date,end:date,accounts:frozenset[str])->SearchTermTrendData:
        if end<start or (end-start).days>92: raise ApiError(code=ErrorCode.VALIDATION_ERROR,status_code=422)
        rows=self.session.execute(select(WalmartAdSearchTermDailyFact.business_date_la,func.sum(WalmartAdSearchTermDailyFact.num_ads_shown),func.sum(WalmartAdSearchTermDailyFact.num_ads_clicks),func.sum(WalmartAdSearchTermDailyFact.ad_spend_amount),func.sum(WalmartAdSearchTermDailyFact.attributed_orders),func.sum(WalmartAdSearchTermDailyFact.advertised_sku_sales_amount),func.sum(WalmartAdSearchTermDailyFact.other_sku_sales_amount)).where(WalmartAdSearchTermDailyFact.source_account_ref.in_(accounts),WalmartAdSearchTermDailyFact.normalized_search_term==normalize_term(term),WalmartAdSearchTermDailyFact.business_date_la.between(start,end)).group_by(WalmartAdSearchTermDailyFact.business_date_la).order_by(WalmartAdSearchTermDailyFact.business_date_la)).all()
        return SearchTermTrendData(items=[SearchTermTrendPoint(business_date_la=x[0],impressions=int(x[1] or 0),clicks=int(x[2] or 0),spend=Decimal(x[3] or 0),orders=Decimal(x[4] or 0),direct_sales=Decimal(x[5] or 0),other_sales=Decimal(x[6] or 0)) for x in rows])
    def create_action(self,p:ActionCreate,actor:str,accounts:frozenset[str])->ActionRead:
        if p.source_account_ref not in accounts: raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED,status_code=403)
        if p.source_fact_id:
            fact=self.session.get(WalmartAdSearchTermDailyFact,p.source_fact_id)
            if fact is None or fact.source_account_ref not in accounts: raise ApiError(code=ErrorCode.NOT_FOUND,status_code=404)
        now=datetime.now(timezone.utc); term=p.search_term.strip()
        row=AdsSearchTermAction(id=uuid4(),source_account_ref=p.source_account_ref,source_fact_id=p.source_fact_id,action_type=p.action_type,search_term=term,normalized_search_term=normalize_term(term),target_scope_json=p.target_scope,status="pending_manual",effect_status="pending",reason=p.reason,created_by=actor,created_at=now,updated_at=now)
        self.session.add(row); self.session.flush()
        self.session.add(AdsSearchTermActionEvent(id=uuid4(),action_id=row.id,event_type="created",actor_ref=actor,detail_json={"provider_write":"not_performed"},created_at=now))
        self.session.commit();self.session.refresh(row);return ActionRead.model_validate(row)
    def list_actions(self,accounts:frozenset[str],page:int,size:int)->ActionListData:
        stmt=select(AdsSearchTermAction).where(AdsSearchTermAction.source_account_ref.in_(accounts))
        total=int(self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows=self.session.scalars(stmt.order_by(AdsSearchTermAction.created_at.desc()).offset((page-1)*size).limit(size)).all()
        return ActionListData(items=[ActionRead.model_validate(x) for x in rows],total=total)
    def complete_action(self,action_id, note:str, actor:str, accounts:frozenset[str])->ActionRead:
        row=self.session.scalar(select(AdsSearchTermAction).where(AdsSearchTermAction.id==action_id,AdsSearchTermAction.source_account_ref.in_(accounts)).with_for_update())
        if row is None: raise ApiError(code=ErrorCode.NOT_FOUND,status_code=404)
        if row.status!="pending_manual": raise ApiError(code="ADS_SEARCH_TERM_ACTION_NOT_PENDING",status_code=409)
        now=datetime.now(timezone.utc);row.status="manually_completed";row.completed_by=actor;row.completion_note=note;row.completed_at=now;row.updated_at=now
        self.session.add(AdsSearchTermActionEvent(id=uuid4(),action_id=row.id,event_type="manual_completion",actor_ref=actor,detail_json={"provider_write":"not_performed"},created_at=now))
        self.session.commit();self.session.refresh(row);return ActionRead.model_validate(row)
