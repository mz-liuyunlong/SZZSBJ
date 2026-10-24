"""Account-scoped persistent SKU library and operator source-event ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode, SuccessEnvelope, success_response
from app.core.auth import Principal
from app.core.permissions import require_permission
from app.db.session import get_db_session
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.products.models import Product

from .analysis_routes import _account_allowed, _require_opted_in_writes
from .models import (
    AiKwAnalysisRun,
    AiKwRunKeyword,
    BizKwMarketObservation,
    BizKwSourceEvent,
    BizSkuKeyword,
    DimKwTerm,
)
from .rule_gates import NORMALIZER_VERSION, normalize_keyword
from .source_bridge import SourceBridgeBlocked, _product_listing

router = APIRouter(tags=["Keyword Planning"])


class LibraryItem(BaseModel):
    term_id: UUID
    keyword: str
    translation: str | None
    status: str
    source_kinds: list[str]
    source_count: int
    observation_count: int
    latest_grade: str | None
    latest_score: int | None


class LibraryRead(BaseModel):
    items: list[LibraryItem]
    total: int
    limit: int
    offset: int
    latest_run_id: UUID | None


class GlobalAssociation(BaseModel):
    product_id: UUID
    sku: str
    status: str
    grade: str | None = None
    score: int | None = None
    exact_selected: bool = False
    broad_selected: bool = False


class GlobalLibraryItem(BaseModel):
    term_id: UUID
    keyword: str
    translation: str | None
    sku_count: int
    associations: list[GlobalAssociation]
    source_kinds: list[str]


class GlobalLibraryRead(BaseModel):
    items: list[GlobalLibraryItem]
    total: int
    limit: int
    offset: int


class ManualWord(BaseModel):
    keyword: str = Field(min_length=1, max_length=255)
    translation: str | None = Field(default=None, max_length=500)


class ManualWordsBody(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    item_id: str = Field(pattern=r"^[0-9]{1,20}$")
    request_key: str = Field(min_length=1, max_length=120)
    words: list[ManualWord] = Field(min_length=1, max_length=100)
    source_kind: Literal["operator_manual"] = "operator_manual"


class ManualWordsRead(BaseModel):
    accepted: int
    source_events_created: int
    status: Literal["review"] = "review"


class TranslationBody(BaseModel):
    source_account_ref: str = Field(min_length=1, max_length=128)
    item_id: str = Field(pattern=r"^[0-9]{1,20}$")
    translation: str = Field(max_length=500)


class TranslationRead(BaseModel):
    term_id: UUID
    translation: str | None


@router.get("/library", response_model=SuccessEnvelope[GlobalLibraryRead, None])
def list_global_library(
    request: Request,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:read"))],
    q: str = "",
    status: str = "all",
    source: str = "all",
    grade: str = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Page distinct terms in one authorized account, then load their SKU links."""
    _account_allowed(source_account_ref, allowed_accounts, principal)
    if (
        status not in ("all", "active", "review", "paused", "excluded")
        or source not in ("all", "excel", "operator_manual")
        or grade not in ("all", "P0", "P1", "P2", "复查", "不投放")
    ):
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=422)
    latest_run_id = (
        select(AiKwAnalysisRun.id)
        .where(
            AiKwAnalysisRun.source_account_ref == source_account_ref,
            AiKwAnalysisRun.product_id == BizSkuKeyword.product_id,
        )
        .order_by(AiKwAnalysisRun.created_at.desc(), AiKwAnalysisRun.id.desc())
        .limit(1)
        .correlate(BizSkuKeyword)
        .scalar_subquery()
    )
    assets = (
        select(BizSkuKeyword.term_id)
        .where(BizSkuKeyword.source_account_ref == source_account_ref)
        .join(Product, Product.id == BizSkuKeyword.product_id)
        .where(Product.deleted_at.is_(None))
    )
    if status != "all":
        assets = assets.where(BizSkuKeyword.status == status)
    if source != "all":
        assets = assets.where(
            select(BizKwSourceEvent.id)
            .where(
                BizKwSourceEvent.source_account_ref == source_account_ref,
                BizKwSourceEvent.product_id == BizSkuKeyword.product_id,
                BizKwSourceEvent.term_id == BizSkuKeyword.term_id,
                BizKwSourceEvent.source_kind == source,
            )
            .exists()
        )
    if grade != "all":
        grade_values = ("复查", "候选复查") if grade == "复查" else (grade,)
        assets = assets.where(
            select(AiKwRunKeyword.id)
            .where(
                AiKwRunKeyword.source_account_ref == source_account_ref,
                AiKwRunKeyword.run_id == latest_run_id,
                AiKwRunKeyword.term_id == BizSkuKeyword.term_id,
                AiKwRunKeyword.allocation_grade.in_(grade_values),
            )
            .exists()
        )
    assets = assets.distinct().subquery()
    terms = select(DimKwTerm).join(assets, assets.c.term_id == DimKwTerm.id)
    if q.strip():
        normalized = normalize_keyword(q)
        terms = terms.where(
            or_(
                DimKwTerm.normalized_keyword.contains(normalized),
                DimKwTerm.translation_default.icontains(q.strip(), autoescape=True),
                select(BizSkuKeyword.id)
                .where(
                    BizSkuKeyword.source_account_ref == source_account_ref,
                    BizSkuKeyword.term_id == DimKwTerm.id,
                    BizSkuKeyword.manual_translation.icontains(q.strip(), autoescape=True),
                )
                .exists(),
            )
        )
    total = session.scalar(select(func.count()).select_from(terms.subquery())) or 0
    page = list(
        session.scalars(
            terms.order_by(DimKwTerm.normalized_keyword, DimKwTerm.id).limit(limit).offset(offset)
        )
    )
    term_ids = [row.id for row in page]
    links = (
        list(
            session.execute(
                select(
                    BizSkuKeyword,
                    Product.sku,
                    AiKwRunKeyword.allocation_grade,
                    AiKwRunKeyword.score,
                    AiKwRunKeyword.exact_selected,
                    AiKwRunKeyword.broad_selected,
                )
                .join(Product, Product.id == BizSkuKeyword.product_id)
                .outerjoin(
                    AiKwRunKeyword,
                    and_(
                        AiKwRunKeyword.source_account_ref == source_account_ref,
                        AiKwRunKeyword.run_id == latest_run_id,
                        AiKwRunKeyword.term_id == BizSkuKeyword.term_id,
                    ),
                )
                .where(
                    BizSkuKeyword.source_account_ref == source_account_ref,
                    BizSkuKeyword.term_id.in_(term_ids),
                    Product.deleted_at.is_(None),
                )
                .order_by(Product.sku, BizSkuKeyword.product_id)
            )
        )
        if term_ids
        else []
    )
    by_term: dict[UUID, list[GlobalAssociation]] = {}
    for asset, sku, allocation_grade, score, exact_selected, broad_selected in links:
        by_term.setdefault(asset.term_id, []).append(
            GlobalAssociation(
                product_id=asset.product_id,
                sku=sku,
                status=asset.status,
                grade=allocation_grade,
                score=score,
                exact_selected=bool(exact_selected),
                broad_selected=bool(broad_selected),
            )
        )
    kinds: dict[UUID, set[str]] = {}
    if term_ids:
        for term_id, kind in session.execute(
            select(
                BizKwSourceEvent.term_id,
                BizKwSourceEvent.source_kind,
            )
            .where(
                BizKwSourceEvent.source_account_ref == source_account_ref,
                BizKwSourceEvent.term_id.in_(term_ids),
            )
            .distinct()
        ):
            kinds.setdefault(term_id, set()).add(kind)
    return success_response(
        request,
        data=GlobalLibraryRead(
            items=[
                GlobalLibraryItem(
                    term_id=term.id,
                    keyword=term.canonical_keyword,
                    translation=term.translation_default,
                    sku_count=len(by_term.get(term.id, [])),
                    associations=by_term.get(term.id, []),
                    source_kinds=sorted(kinds.get(term.id, set())),
                )
                for term in page
            ],
            total=int(total),
            limit=limit,
            offset=offset,
        ),
        meta=None,
    )


@router.get(
    "/products/{product_id}/library",
    response_model=SuccessEnvelope[LibraryRead, None],
)
def list_library(
    request: Request,
    product_id: UUID,
    source_account_ref: Annotated[str, Query(min_length=1, max_length=128)],
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:read"))],
    q: str = "",
    status: str = "all",
    source: str = "all",
    grade: str = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    _account_allowed(source_account_ref, allowed_accounts, principal)
    query = (
        select(BizSkuKeyword, DimKwTerm)
        .join(
            DimKwTerm,
            DimKwTerm.id == BizSkuKeyword.term_id,
        )
        .where(
            BizSkuKeyword.source_account_ref == source_account_ref,
            BizSkuKeyword.product_id == product_id,
        )
    )
    if q.strip():
        query = query.where(
            or_(
                DimKwTerm.normalized_keyword.contains(normalize_keyword(q)),
                BizSkuKeyword.manual_translation.icontains(q.strip(), autoescape=True),
                DimKwTerm.translation_default.icontains(q.strip(), autoescape=True),
            )
        )
    if status != "all":
        if status not in ("active", "review", "paused", "excluded"):
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=422)
        query = query.where(BizSkuKeyword.status == status)
    if source != "all":
        if source not in ("excel", "operator_manual"):
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=422)
        query = query.where(
            select(BizKwSourceEvent.id)
            .where(
                BizKwSourceEvent.source_account_ref == source_account_ref,
                BizKwSourceEvent.product_id == product_id,
                BizKwSourceEvent.term_id == BizSkuKeyword.term_id,
                BizKwSourceEvent.source_kind == source,
            )
            .exists()
        )
    if grade != "all":
        if grade not in ("P0", "P1", "P2", "复查", "不投放"):
            raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=422)
        latest_run_id = (
            select(AiKwAnalysisRun.id)
            .where(
                AiKwAnalysisRun.source_account_ref == source_account_ref,
                AiKwAnalysisRun.product_id == product_id,
            )
            .order_by(AiKwAnalysisRun.created_at.desc(), AiKwAnalysisRun.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        grade_values = ("复查", "候选复查") if grade == "复查" else (grade,)
        query = query.where(
            select(AiKwRunKeyword.id)
            .where(
                AiKwRunKeyword.source_account_ref == source_account_ref,
                AiKwRunKeyword.run_id == latest_run_id,
                AiKwRunKeyword.term_id == BizSkuKeyword.term_id,
                AiKwRunKeyword.allocation_grade.in_(grade_values),
            )
            .exists()
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        session.execute(
            query.order_by(
                DimKwTerm.normalized_keyword.asc(),
                BizSkuKeyword.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
    )
    ids = [asset.term_id for asset, _ in rows]
    event_rows = session.execute(
        select(
            BizKwSourceEvent.term_id,
            BizKwSourceEvent.source_kind,
            func.count(BizKwSourceEvent.id),
        )
        .where(
            BizKwSourceEvent.source_account_ref == source_account_ref,
            BizKwSourceEvent.product_id == product_id,
            BizKwSourceEvent.term_id.in_(ids),
        )
        .group_by(BizKwSourceEvent.term_id, BizKwSourceEvent.source_kind)
    )
    sources: dict[UUID, list[tuple[str, int]]] = {}
    for term_id, source, count in event_rows:
        sources.setdefault(term_id, []).append((source, int(count)))
    observations = dict(
        session.execute(
            select(
                BizKwMarketObservation.term_id,
                func.count(BizKwMarketObservation.id),
            )
            .where(
                BizKwMarketObservation.source_account_ref == source_account_ref,
                BizKwMarketObservation.product_id == product_id,
                BizKwMarketObservation.term_id.in_(ids),
            )
            .group_by(BizKwMarketObservation.term_id)
        ).all()
    )
    latest = session.scalar(
        select(AiKwAnalysisRun.id)
        .where(
            AiKwAnalysisRun.source_account_ref == source_account_ref,
            AiKwAnalysisRun.product_id == product_id,
        )
        .order_by(AiKwAnalysisRun.created_at.desc(), AiKwAnalysisRun.id.desc())
        .limit(1)
    )
    grades = (
        {
            row.term_id: row
            for row in session.scalars(
                select(AiKwRunKeyword).where(
                    AiKwRunKeyword.source_account_ref == source_account_ref,
                    AiKwRunKeyword.run_id == latest,
                    AiKwRunKeyword.term_id.in_(ids),
                )
            )
        }
        if latest
        else {}
    )
    items = [
        LibraryItem(
            term_id=asset.term_id,
            keyword=term.canonical_keyword,
            translation=asset.manual_translation or term.translation_default,
            status=asset.status,
            source_kinds=sorted(source for source, _ in sources.get(asset.term_id, [])),
            source_count=sum(count for _, count in sources.get(asset.term_id, [])),
            observation_count=int(observations.get(asset.term_id, 0)),
            latest_grade=grades[asset.term_id].allocation_grade
            if asset.term_id in grades
            else None,
            latest_score=grades[asset.term_id].score if asset.term_id in grades else None,
        )
        for asset, term in rows
    ]
    return success_response(
        request,
        data=LibraryRead(
            items=items,
            total=int(total),
            limit=limit,
            offset=offset,
            latest_run_id=latest,
        ),
        meta=None,
    )


@router.patch(
    "/products/{product_id}/library/{term_id}/translation",
    response_model=SuccessEnvelope[TranslationRead, None],
)
def update_library_translation(
    request: Request,
    product_id: UUID,
    term_id: UUID,
    body: TranslationBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:write"))],
):
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _require_opted_in_writes()
    if session.new or session.dirty or session.deleted:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    session.rollback()
    try:
        with session.begin():
            _product_listing(session, body.source_account_ref, product_id, body.item_id)
            asset = session.scalar(
                select(BizSkuKeyword)
                .where(
                    BizSkuKeyword.source_account_ref == body.source_account_ref,
                    BizSkuKeyword.product_id == product_id,
                    BizSkuKeyword.term_id == term_id,
                )
                .with_for_update()
            )
            if asset is None:
                raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
            asset.manual_translation = body.translation.strip() or None
            asset.confirmed_by = principal.user_id
            asset.updated_at = datetime.now(UTC)
    except SourceBridgeBlocked as exc:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=409, details={"reason_code": str(exc)}
        ) from exc
    return success_response(
        request,
        data=TranslationRead(term_id=term_id, translation=asset.manual_translation),
        meta=None,
    )


@router.post(
    "/products/{product_id}/library/manual",
    response_model=SuccessEnvelope[ManualWordsRead, None],
)
def add_manual_words(
    request: Request,
    product_id: UUID,
    body: ManualWordsBody,
    session: Annotated[Session, Depends(get_db_session)],
    allowed_accounts: Annotated[frozenset[str], Depends(require_source_account_scope)],
    principal: Annotated[Principal, Depends(require_permission("products:write"))],
):
    _account_allowed(body.source_account_ref, allowed_accounts, principal)
    _require_opted_in_writes()
    normalized = [normalize_keyword(word.keyword) for word in body.words]
    if (
        not all(normalized)
        or len(set(normalized)) != len(normalized)
        or any(len(value) > 255 for value in normalized)
    ):
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=422,
            details={"reason_code": "MANUAL_WORDS_INVALID_OR_DUPLICATED"},
        )
    if session.new or session.dirty or session.deleted:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=409)
    session.rollback()
    try:
        with session.begin():
            _product_listing(session, body.source_account_ref, product_id, body.item_id)
            created = 0
            for word, term_key in zip(body.words, normalized, strict=True):
                session.execute(
                    pg_insert(DimKwTerm)
                    .values(
                        id=uuid4(),
                        canonical_keyword=word.keyword.strip(),
                        normalized_keyword=term_key,
                        normalization_version=NORMALIZER_VERSION,
                    )
                    .on_conflict_do_nothing(index_elements=["normalized_keyword"])
                )
                term = session.scalar(
                    select(DimKwTerm).where(
                        DimKwTerm.normalized_keyword == term_key,
                    )
                )
                assert term is not None
                session.execute(
                    pg_insert(BizSkuKeyword)
                    .values(
                        id=uuid4(),
                        source_account_ref=body.source_account_ref,
                        product_id=product_id,
                        term_id=term.id,
                        status="review",
                        manual_translation=word.translation,
                    )
                    .on_conflict_do_nothing(index_elements=["product_id", "term_id"])
                )
                asset = session.scalar(
                    select(BizSkuKeyword).where(
                        BizSkuKeyword.product_id == product_id,
                        BizSkuKeyword.term_id == term.id,
                    )
                )
                if asset is None or asset.source_account_ref != body.source_account_ref:
                    raise SourceBridgeBlocked("LIBRARY_ACCOUNT_CONFLICT")
                event_key = f"manual:{body.request_key}:{term.id}"
                result = session.execute(
                    pg_insert(BizKwSourceEvent)
                    .values(
                        id=uuid4(),
                        source_account_ref=body.source_account_ref,
                        product_id=product_id,
                        term_id=term.id,
                        source_kind="operator_manual",
                        source_event_key=event_key,
                        source_reference=None,
                        store_id=None,
                        evidence_json={
                            "actor_ref": principal.user_id,
                            "request_key": body.request_key,
                        },
                        discovered_at=datetime.now(UTC),
                    )
                    .on_conflict_do_nothing(constraint="uq_biz_kw_source_event_dedupe")
                )
                created += int(result.rowcount or 0)
    except SourceBridgeBlocked as exc:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=409, details={"reason_code": str(exc)}
        ) from exc
    return success_response(
        request,
        data=ManualWordsRead(
            accepted=len(body.words),
            source_events_created=created,
        ),
        meta=None,
    )
