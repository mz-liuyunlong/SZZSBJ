from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import app.modules.sku_detail.publisher as publisher_module
from app.modules.integration_sync.parsers.lingxing_product_info import (
    ParsedImage,
    ParsedSkuDetail,
    ParsedTag,
)
from app.modules.sku_detail.business_hash import product_info_business_hash
from app.modules.sku_detail.publisher import SkuDetailPublicationService


def _detail(
    *,
    purchase_cost_cny: Decimal = Decimal("12.3400"),
    images: tuple[ParsedImage, ...] | None = None,
    tags: tuple[ParsedTag, ...] | None = None,
) -> ParsedSkuDetail:
    return ParsedSkuDetail(
        product_name="Synthetic Product",
        lingxing_sku_code="SYNTHETIC-SKU",
        main_image_url="https://example.invalid/main.jpg",
        product_developer_name="Synthetic Developer",
        product_developer_uid="developer-1",
        purchase_delivery_days=7,
        purchase_cost_cny=purchase_cost_cny,
        purchase_cost_currency_code="CNY",
        purchase_material="Synthetic Material",
        customs_export_name_cn="Synthetic CN",
        customs_import_name_en="Synthetic EN",
        customs_declared_unit_price=Decimal("3.2100"),
        customs_declared_currency=None,
        china_hs_code="001234",
        owner_uid="owner-1",
        owner_name="Synthetic Owner",
        clearance_material_cn="Synthetic CN Material",
        clearance_usage_cn="Synthetic Usage",
        clearance_material_en="Synthetic EN Material",
        us_first_leg_cost=Decimal("8.0000"),
        us_first_leg_currency="USD",
        product_length_cm=Decimal("10"),
        product_width_cm=Decimal("5"),
        product_height_cm=Decimal("2"),
        product_net_weight_g=Decimal("500"),
        package_length_cm=Decimal("11"),
        package_width_cm=Decimal("6"),
        package_height_cm=Decimal("3"),
        box_length_cm=Decimal("40"),
        box_width_cm=Decimal("30"),
        box_height_cm=Decimal("20"),
        box_pcs=4,
        product_gross_weight_g=Decimal("600"),
        box_weight_kg=Decimal("8"),
        images=images
        if images is not None
        else (
            ParsedImage(
                ordinal=0,
                pic_url="https://example.invalid/one.jpg",
                is_primary=True,
            ),
        ),
        tags=tags
        if tags is not None
        else (
            ParsedTag(
                ordinal=0,
                global_tag_id="tag-1",
                tag_name="Synthetic Tag",
                color="blue",
            ),
        ),
    )


def test_business_hash_is_deterministic_and_normalizes_decimal_scale() -> None:
    left = product_info_business_hash(_detail(purchase_cost_cny=Decimal("1.0")))
    right = product_info_business_hash(_detail(purchase_cost_cny=Decimal("1.0000")))

    assert left == right
    assert len(left) == 64


def test_business_hash_preserves_image_order_semantics() -> None:
    first = ParsedImage(
        ordinal=0,
        pic_url="https://example.invalid/one.jpg",
        is_primary=True,
    )
    second = ParsedImage(
        ordinal=1,
        pic_url="https://example.invalid/two.jpg",
        is_primary=False,
    )
    swapped_first = ParsedImage(
        ordinal=0,
        pic_url=second.pic_url,
        is_primary=second.is_primary,
    )
    swapped_second = ParsedImage(
        ordinal=1,
        pic_url=first.pic_url,
        is_primary=first.is_primary,
    )

    assert product_info_business_hash(
        _detail(images=(first, second))
    ) != product_info_business_hash(_detail(images=(swapped_first, swapped_second)))


def test_business_hash_ignores_tag_order_but_detects_tag_content_change() -> None:
    first = ParsedTag(ordinal=0, global_tag_id="tag-a", tag_name="A", color="blue")
    second = ParsedTag(ordinal=1, global_tag_id="tag-b", tag_name="B", color="green")
    reordered = (
        ParsedTag(ordinal=0, global_tag_id="tag-b", tag_name="B", color="green"),
        ParsedTag(ordinal=1, global_tag_id="tag-a", tag_name="A", color="blue"),
    )
    changed = (
        ParsedTag(ordinal=0, global_tag_id="tag-a", tag_name="A", color="red"),
        second,
    )

    baseline = product_info_business_hash(_detail(tags=(first, second)))
    assert baseline == product_info_business_hash(_detail(tags=reordered))
    assert baseline != product_info_business_hash(_detail(tags=changed))


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _FakeSyncRepository:
    def __init__(
        self,
        *,
        run_id: UUID,
        raw_request_ref_id: UUID,
        identity: object,
    ) -> None:
        self.run_id = run_id
        self.raw_request_ref_id = raw_request_ref_id
        self.identity = identity
        self.raw_ref = SimpleNamespace(
            id=raw_request_ref_id,
            run_id=run_id,
            raw_blob_id=uuid4(),
        )
        self.parse_job = None
        self.lineage: list[object] = []
        self.events: list[object] = []

    def get_lingxing_identity(self, source_account_ref: str, lingxing_sku_id: str) -> object:
        del source_account_ref, lingxing_sku_id
        return self.identity

    def get_raw_request_ref(self, raw_request_ref_id: UUID) -> object | None:
        return self.raw_ref if raw_request_ref_id == self.raw_request_ref_id else None

    def get_parse_job(
        self, raw_request_ref_id: UUID, parser_key: str, parser_version: str
    ) -> object:
        del raw_request_ref_id, parser_key, parser_version
        return self.parse_job

    def add_parse_job(self, parse_job: object) -> object:
        self.parse_job = parse_job
        return parse_job

    def add_lineage(self, entries: list[object]) -> None:
        self.lineage.extend(entries)

    def next_event_sequence(self, run_id: UUID) -> int:
        del run_id
        return len(self.events) + 1

    def add_event(self, event: object) -> object:
        self.events.append(event)
        return event


class _FakeSkuRepository:
    def __init__(self, *, identity: object, current: object | None) -> None:
        self.identity = identity
        self.current = current
        self.profile = None
        self.snapshots: list[object] = []
        self.images: list[object] = []
        self.tags: list[object] = []
        self.identity_locks = 0

    def get_identity_for_update(self, identity_id: UUID) -> object | None:
        assert self.identity.id == identity_id
        self.identity_locks += 1
        return self.identity

    def get_current(self, identity_id: UUID) -> object | None:
        assert self.identity.id == identity_id
        return self.current

    def add_snapshot(self, snapshot: object) -> object:
        self.snapshots.append(snapshot)
        return snapshot

    def add_images(self, images: tuple[object, ...] | list[object]) -> list[object]:
        values = list(images)
        self.images.extend(values)
        return values

    def add_tags(self, tags: tuple[object, ...] | list[object]) -> list[object]:
        values = list(tags)
        self.tags.extend(values)
        return values

    def add_current(self, current: object) -> object:
        self.current = current
        return current

    def get_profile(self, identity_id: UUID) -> object | None:
        assert self.identity.id == identity_id
        return self.profile

    def add_profile(self, profile: object) -> object:
        self.profile = profile
        return profile

    def update_record(self, record: object, values: dict[str, object]) -> object:
        for name, value in values.items():
            setattr(record, name, value)
        return record


class _FakeMediaRegistration:
    calls = 0

    def __init__(self, session: object) -> None:
        del session

    def register_images(self, images: list[object]) -> list[UUID]:
        type(self).calls += 1
        return [uuid4() for _ in images]


@pytest.fixture(autouse=True)
def reset_media_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[UUID, ...]]:
    _FakeMediaRegistration.calls = 0
    dispatched: list[tuple[UUID, ...]] = []
    monkeypatch.setattr(
        publisher_module,
        "MediaAssetRegistrationService",
        _FakeMediaRegistration,
    )
    monkeypatch.setattr(
        publisher_module,
        "dispatch_media_assets",
        lambda asset_ids: dispatched.append(tuple(asset_ids)),
    )
    return dispatched


def _service(
    *,
    current: object | None,
) -> tuple[
    SkuDetailPublicationService,
    _FakeSession,
    _FakeSyncRepository,
    _FakeSkuRepository,
    UUID,
    UUID,
]:
    run_id = uuid4()
    raw_request_ref_id = uuid4()
    identity = SimpleNamespace(id=uuid4(), lingxing_sku_code="SYNTHETIC-SKU")
    session = _FakeSession()
    service = SkuDetailPublicationService(session)  # type: ignore[arg-type]
    sync_repository = _FakeSyncRepository(
        run_id=run_id,
        raw_request_ref_id=raw_request_ref_id,
        identity=identity,
    )
    sku_repository = _FakeSkuRepository(identity=identity, current=current)
    service.sync_repository = sync_repository  # type: ignore[assignment]
    service.repository = sku_repository  # type: ignore[assignment]
    return service, session, sync_repository, sku_repository, run_id, raw_request_ref_id


def test_publish_with_result_skips_normalized_writes_when_business_is_unchanged(
    reset_media_calls: list[tuple[UUID, ...]],
) -> None:
    parsed = _detail()
    existing_snapshot_id = uuid4()
    current = SimpleNamespace(
        id=uuid4(),
        source_snapshot_id=existing_snapshot_id,
        source_observed_at=datetime(2026, 9, 15, tzinfo=UTC),
        business_hash=product_info_business_hash(parsed),
    )
    service, session, sync_repository, repository, run_id, raw_ref_id = _service(current=current)

    result = service.publish_with_result(
        run_id=run_id,
        raw_request_ref_id=raw_ref_id,
        source_account_ref="synthetic-account",
        lingxing_sku_id="synthetic-id",
        source_observed_at=datetime(2026, 9, 16, tzinfo=UTC),
        parser_version="v1",
        parsed=parsed,
    )

    assert result.status == "unchanged"
    assert result.snapshot_id == existing_snapshot_id
    assert result.images_written == 0
    assert result.tags_written == 0
    assert repository.identity_locks == 1
    assert repository.snapshots == []
    assert repository.images == []
    assert repository.tags == []
    assert repository.profile is None
    assert _FakeMediaRegistration.calls == 0
    assert reset_media_calls == []
    assert session.commits == 1
    assert sync_repository.parse_job is not None
    assert sync_repository.parse_job.records_seen == 1
    assert sync_repository.parse_job.records_written == 0
    assert sync_repository.lineage == []
    assert sync_repository.events[-1].message_code == "PRODUCT_INFO_UNCHANGED"


def test_publish_with_result_writes_changed_snapshot_and_keeps_publish_compatible(
    reset_media_calls: list[tuple[UUID, ...]],
) -> None:
    parsed = _detail()
    service, session, sync_repository, repository, run_id, raw_ref_id = _service(current=None)

    result = service.publish_with_result(
        run_id=run_id,
        raw_request_ref_id=raw_ref_id,
        source_account_ref="synthetic-account",
        lingxing_sku_id="synthetic-id",
        source_observed_at=datetime(2026, 9, 16, tzinfo=UTC),
        parser_version="v1",
        parsed=parsed,
    )

    assert result.status == "changed"
    assert result.business_hash == product_info_business_hash(parsed)
    assert len(repository.snapshots) == 1
    assert repository.snapshots[0].business_hash == result.business_hash
    assert result.snapshot_id == repository.snapshots[0].id
    assert result.images_written == len(parsed.images)
    assert result.tags_written == len(parsed.tags)
    assert repository.current.business_hash == result.business_hash
    assert repository.profile is not None
    assert _FakeMediaRegistration.calls == 1
    assert len(reset_media_calls) == 1
    assert session.commits == 1
    assert sync_repository.parse_job.records_written == 1
    assert sync_repository.lineage
    assert sync_repository.events[-1].message_code == "PARSE_JOB_SUCCEEDED"

    second_raw_ref = uuid4()
    sync_repository.raw_request_ref_id = second_raw_ref
    sync_repository.raw_ref = SimpleNamespace(
        id=second_raw_ref,
        run_id=run_id,
        raw_blob_id=uuid4(),
    )
    sync_repository.parse_job = None
    snapshot_id = service.publish(
        run_id=run_id,
        raw_request_ref_id=second_raw_ref,
        source_account_ref="synthetic-account",
        lingxing_sku_id="synthetic-id",
        source_observed_at=datetime(2026, 9, 17, tzinfo=UTC),
        parser_version="v1",
        parsed=parsed,
    )
    assert snapshot_id == result.snapshot_id
    assert len(repository.snapshots) == 1


def test_legacy_current_without_hash_is_treated_as_changed(
    reset_media_calls: list[tuple[UUID, ...]],
) -> None:
    parsed = _detail()
    current = SimpleNamespace(
        id=uuid4(),
        source_snapshot_id=uuid4(),
        source_observed_at=datetime(2026, 9, 15, tzinfo=UTC),
        business_hash=None,
    )
    service, _, _, repository, run_id, raw_ref_id = _service(current=current)

    result = service.publish_with_result(
        run_id=run_id,
        raw_request_ref_id=raw_ref_id,
        source_account_ref="synthetic-account",
        lingxing_sku_id="synthetic-id",
        source_observed_at=datetime(2026, 9, 16, tzinfo=UTC),
        parser_version="v1",
        parsed=parsed,
    )

    assert result.status == "changed"
    assert len(repository.snapshots) == 1
    assert repository.current.business_hash == result.business_hash
    assert _FakeMediaRegistration.calls == 1
    assert len(reset_media_calls) == 1
