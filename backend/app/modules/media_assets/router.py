"""Signed same-origin delivery route for cached media derivatives."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorEnvelope
from app.db.session import get_db_session
from app.modules.media_assets.read_service import (
    MediaAssetDeliveryService,
    MediaDeliveryError,
)
from app.modules.media_assets.schemas import MediaVariant
from app.modules.media_assets.signing import MediaSignatureError

router = APIRouter(prefix="/api/media/image-assets", tags=["Media Assets"])
db_session = Annotated[Session, Depends(get_db_session)]

ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}


@router.get(
    "/{asset_id}/{variant}",
    responses=ERRORS,
    response_class=FileResponse,
    operation_id="getSignedMediaImageVariant",
)
def get_media_image_variant(
    asset_id: UUID,
    variant: MediaVariant,
    session: db_session,
    expires: Annotated[int, Query(gt=0)],
    signature: Annotated[str, Query()],
) -> FileResponse:
    try:
        delivery = MediaAssetDeliveryService.from_runtime(session).resolve(
            asset_id,
            variant,
            expires=expires,
            signature=signature,
        )
    except MediaSignatureError as exc:
        raise ApiError(code=exc.code, status_code=403) from None
    except MediaDeliveryError:
        raise ApiError(code="MEDIA_NOT_AVAILABLE", status_code=404) from None

    return FileResponse(
        delivery.path,
        media_type="image/webp",
        headers={
            "Cache-Control": f"private, max-age={delivery.max_age_seconds}, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
