import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.modules.integration_sync.models import (
    IntegrationSyncRunWorkItem,
    LingxingProductInfoBatchItem,
)


class BatchProductInfoOutboundDisabled(RuntimeError):
    """V1 deliberately has no real batchGetProductInfo transport contract."""


@dataclass(frozen=True, slots=True)
class BatchPlan:
    work_items: tuple[IntegrationSyncRunWorkItem, ...]
    batch_items: tuple[LingxingProductInfoBatchItem, ...]


class LingxingBatchGetProductInfoSyncHandler:
    handler_key = "lingxing.batch_get_product_info.v1"
    request_kind = "id_batch_page"

    def build_plan(
        self,
        *,
        run_id: UUID,
        source_account_ref: str,
        lingxing_sku_ids: list[str],
        batch_size: int,
    ) -> BatchPlan:
        if not 1 <= batch_size <= 10_000:
            raise ValueError("batch_size is outside the implementation bound")
        ordered_ids = sorted(lingxing_sku_ids)
        if not ordered_ids or len(set(ordered_ids)) != len(ordered_ids):
            raise ValueError("active SKU identity set must be nonempty and unique")
        work_items: list[IntegrationSyncRunWorkItem] = []
        memberships: list[LingxingProductInfoBatchItem] = []
        for batch_index, start in enumerate(range(0, len(ordered_ids), batch_size), start=1):
            ids = ordered_ids[start : start + batch_size]
            digest = ordered_id_hash(ids)
            work_item = IntegrationSyncRunWorkItem(
                id=uuid4(),
                run_id=run_id,
                ordinal=batch_index,
                request_kind=self.request_kind,
                status="queued",
                attempt_count=0,
                batch_no=batch_index,
                id_count=len(ids),
                id_hash=digest,
                request_safe_params={
                    "batch_no": batch_index,
                    "id_count": len(ids),
                    "id_hash": digest,
                },
            )
            work_items.append(work_item)
            memberships.extend(
                LingxingProductInfoBatchItem(
                    id=uuid4(),
                    run_id=run_id,
                    work_item_id=work_item.id,
                    source_account_ref=source_account_ref,
                    batch_no=batch_index,
                    item_ordinal=item_ordinal,
                    lingxing_sku_id=sku_id,
                    item_status="queued",
                )
                for item_ordinal, sku_id in enumerate(ids)
            )
        return BatchPlan(tuple(work_items), tuple(memberships))

    def execute(self, run_id: UUID) -> None:
        del run_id
        raise BatchProductInfoOutboundDisabled(
            "batchGetProductInfo outbound execution is not authorized"
        )


def ordered_id_hash(values: list[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()
