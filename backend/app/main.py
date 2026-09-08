from typing import Literal

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel

from app.core.api import SuccessEnvelope, install_api_foundation, success_response
from app.core.auth import enforce_protected_by_default


class HealthData(BaseModel):
    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    application = FastAPI(
        title="YC System API",
        dependencies=[Depends(enforce_protected_by_default)],
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    install_api_foundation(application)

    @application.get("/health", response_model=SuccessEnvelope[HealthData, None])
    def health_check(request: Request) -> SuccessEnvelope[HealthData, None]:
        return success_response(request, data=HealthData(), meta=None)

    return application


app = create_app()
