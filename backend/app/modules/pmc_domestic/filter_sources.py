"""Shared current product ownership; ambiguity never chooses an arbitrary identity."""

from sqlalchemy import and_, func, select
from sqlalchemy.sql.selectable import Subquery

from app.modules.sku_detail.models import LingxingSkuIdentity, LingxingSkuProductInfoCurrent

OWNER_OBJECTS = ["dwd_lingxing_sku_identity_index", "dwd_lingxing_sku_product_info_current"]


def current_product_owners(accounts: frozenset[str]) -> Subquery:
    """Reject ambiguous SKU identities before filtering, even if their UIDs agree."""
    identity = LingxingSkuIdentity
    info = LingxingSkuProductInfoCurrent
    return (
        select(
            identity.source_account_ref.label("account"),
            identity.lingxing_sku_code.label("sku"),
            func.max(info.owner_uid).label("uid"),
            func.max(func.nullif(func.trim(info.owner_name), "")).label("name"),
        )
        .outerjoin(
            info,
            and_(
                info.identity_id == identity.id,
                info.lingxing_sku_id == identity.lingxing_sku_id,
                info.provider == identity.provider,
                info.source_account_ref == identity.source_account_ref,
            ),
        )
        .where(identity.source_account_ref.in_(sorted(accounts)), identity.is_active.is_(True))
        .group_by(identity.source_account_ref, identity.lingxing_sku_code)
        .having(
            func.count(func.distinct(identity.id)) == 1,
            func.count(func.distinct(info.owner_uid)) == 1,
            func.trim(func.max(info.owner_uid)) != "",
        )
        .subquery()
    )
