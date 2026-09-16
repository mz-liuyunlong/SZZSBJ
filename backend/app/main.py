from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel

from app.core.api import SuccessEnvelope, install_api_foundation, success_response
from app.core.auth import enforce_protected_by_default
from app.db.session import dispose_engine
from app.modules.data_pages.router import router as data_pages_router
from app.modules.integration_sync.router import router as integration_sync_router
from app.modules.media_assets.router import router as media_assets_router
from app.modules.product_management.router import router as product_management_router
from app.modules.products.router import router as products_router
from app.modules.sku_detail.router import router as sku_detail_router


class HealthData(BaseModel):
    status: Literal["ok"] = "ok"


@asynccontextmanager
async def app_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    dispose_engine()


def create_app() -> FastAPI:
    application = FastAPI(
        title="YC System API",
        dependencies=[Depends(enforce_protected_by_default)],
        docs_url=None,
        lifespan=app_lifespan,
        redoc_url=None,
        openapi_url=None,
    )
    install_api_foundation(application)
    application.include_router(data_pages_router)
    application.include_router(integration_sync_router)
    application.include_router(media_assets_router)
    application.include_router(product_management_router)
    application.include_router(products_router)
    application.include_router(sku_detail_router)

    @application.get("/health", response_model=SuccessEnvelope[HealthData, None])
    def health_check(request: Request) -> SuccessEnvelope[HealthData, None]:
        return success_response(request, data=HealthData(), meta=None)

    return application


app = create_app()
