from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.lingxing.client import (
    LingxingCaptureRequest,
    LingxingRawEnvelope,
    LingxingReadonlyClient,
)
from app.integrations.lingxing.security import raw_hash, redact_json, redact_text
from app.models.raw_lingxing_api import RawLingxingApi
from app.repositories.lingxing_raw import LingxingRawRepository


class LingxingWriteError(RuntimeError):
    """Safe RAW write error."""


@dataclass(frozen=True)
class LingxingRawWriteResult:
    written: bool
    raw_hash: str
    record_id: int | None


class LingxingRawWriter:
    def __init__(self, repository: LingxingRawRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def write(self, envelope: LingxingRawEnvelope) -> LingxingRawWriteResult:
        if self.settings.lingxing_allow_structured_write:
            raise LingxingWriteError("Lingxing structured writes are not approved")

        request_params = redact_json(envelope.request_params_json)
        request_body = redact_json(envelope.request_body_json)
        response = redact_json(envelope.response_json)
        extra = redact_json(envelope.extra_json)
        error_code = self._safe_optional_text(envelope.error_code)
        error_message = self._safe_optional_text(envelope.error_message, limit=1_000)
        digest = raw_hash(
            api_path=envelope.api_path,
            request_method=envelope.request_method,
            request_params=request_params,
            request_body=request_body,
            response=response,
            data_date=envelope.data_date,
        )

        if self.settings.lingxing_dry_run:
            return LingxingRawWriteResult(written=False, raw_hash=digest, record_id=None)
        if not self.settings.lingxing_save_raw or not self.settings.lingxing_allow_raw_write:
            raise LingxingWriteError("Lingxing RAW writes are disabled")

        record = self.repository.add(
            RawLingxingApi(
                source_system="lingxing",
                api_path=envelope.api_path,
                request_method=envelope.request_method,
                request_params_json=request_params,
                request_body_json=request_body,
                response_json=response,
                response_code=envelope.response_code,
                is_success=envelope.is_success,
                error_code=error_code,
                error_message=error_message,
                data_date=envelope.data_date,
                pulled_at=envelope.pulled_at,
                raw_hash=digest,
                page_no=envelope.page_no,
                page_size=envelope.page_size,
                store_id=envelope.store_id,
                store_name=envelope.store_name,
                object_type=envelope.object_type,
                trace_id=envelope.trace_id,
                run_id=envelope.run_id,
                batch_id=envelope.batch_id,
                attempt_no=envelope.attempt_no,
                extra_json=extra,
            )
        )
        return LingxingRawWriteResult(written=True, raw_hash=digest, record_id=record.id)

    @staticmethod
    def _safe_optional_text(value: str | None, *, limit: int | None = None) -> str | None:
        if value is None:
            return None
        safe = redact_text(value)
        return safe[:limit] if limit is not None else safe


class LingxingRawService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.repository = LingxingRawRepository(session)
        self.writer = LingxingRawWriter(self.repository, settings)

    def capture(
        self,
        client: LingxingReadonlyClient,
        request: LingxingCaptureRequest,
    ) -> list[LingxingRawWriteResult]:
        return self.save(client.fetch_pages(request))

    def save(self, envelopes: list[LingxingRawEnvelope]) -> list[LingxingRawWriteResult]:
        results = [self.writer.write(envelope) for envelope in envelopes]
        if any(result.written for result in results):
            self.session.commit()
        return results
