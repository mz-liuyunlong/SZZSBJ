"""Resolve SCF store identity from the persisted Lingxing store dimension.

The Lingxing source account (typically primary) is NOT a store identity.
Require an explicit store RBAC grant, an approved store-code mapping, and a
matching active Walmart store dimension row before dispatch.
"""
from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.core.auth import PREVIEW_PRINCIPAL_ID, Principal, require_principal
from app.db.session import get_db_session
from app.modules.data_pages.models import LingxingStoreDimension
from app.modules.iam.rbac_repository import RbacRepository
from app.modules.integration_sync.dependencies import require_source_account_scope

SourceScope = Annotated[frozenset[str], Depends(require_source_account_scope)]
DbSession = Annotated[Session, Depends(get_db_session)]


def verify_store(
    *,
    session: Session,
    source_account_ref: str,
    store_id: str,
    store_code: str,
) -> None:
    """Fail closed if store identity is missing, stale, ambiguous or inconsistent."""
    matches = session.scalars(
        select(LingxingStoreDimension).where(
            LingxingStoreDimension.source_account_ref == source_account_ref,
            LingxingStoreDimension.store_id == store_id,
            LingxingStoreDimension.platform_code == "walmart",
            LingxingStoreDimension.is_sync.is_(True),
        )
    ).all()
    if len(matches) != 1:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    name = matches[0].store_name or ""
    if not name.startswith(store_code + "-"):
        raise ApiError(code="WALMART_SCF_STORE_IDENTITY_MISMATCH", status_code=503)


def verify_store_grant(
    *,
    principal: Principal,
    session: Session,
    store_id: str,
) -> None:
    # No implicit grant from source_account=primary or general execute permission.
    if principal.user_id == PREVIEW_PRINCIPAL_ID:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    try:
        user_id = int(principal.user_id)
    except (TypeError, ValueError):
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403) from None
    grants = RbacRepository(session).resolve_user_data_scope(
        user_id=user_id, scope_type="store"
    )
    if store_id not in grants and "*" not in grants:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)


def verify_http_store(
    *,
    principal: Principal,
    session: Session,
    source_account_ref: str,
    store_id: str,
    verified_source_account_scope: frozenset[str],
    store_code: str,
) -> None:
    if source_account_ref not in verified_source_account_scope:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
    verify_store_grant(principal=principal, session=session, store_id=store_id)
    verify_store(
        session=session,
        source_account_ref=source_account_ref,
        store_id=store_id,
        store_code=store_code,
    )
