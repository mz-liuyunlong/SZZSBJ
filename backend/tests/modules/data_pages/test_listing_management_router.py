import json
from collections import namedtuple
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.data_pages.models import ProductCustomTag
from app.modules.data_pages.repository import (
    ListingManagementRepository,
    ListingTagRepository,
    _csv_values,
)
from app.modules.data_pages.schemas import (
    ListingManagementItemRead,
    ListingManagementListData,
    ListingManagementQuery,
    ListingTagBatchSetData,
    ListingTagRead,
)
from app.modules.data_pages.service import ListingManagementService
from app.modules.integration_sync.dependencies import require_source_account_scope

ALL_PERMISSIONS = frozenset({"page:products:listing-management:view"})
NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)


def _app(*permissions: str) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=frozenset(permissions) if permissions else ALL_PERMISSIONS,
    )
    application.dependency_overrides[require_source_account_scope] = lambda: frozenset(
        {"synthetic-account"}
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    return application


def _assert_envelope(response: Any, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status
    body: dict[str, Any] = response.json()
    assert set(body) == {"success", "data", "error", "meta", "request_id"}
    assert response.headers["X-Request-ID"] == body["request_id"]
    return body


def _listing_item() -> ListingManagementItemRead:
    return ListingManagementItemRead(
        id="00000000-0000-0000-0000-000000000003",
        source_account_ref="synthetic-account",
        platform_code="10008",
        store_id="store-1",
        store_name="Walmart US",
        item_id="item-1",
        msku="msku-1",
        local_sku="sku-1",
        local_name="Synthetic Listing",
        title="Synthetic Listing Title",
        picture_url="https://example.invalid/listing.jpg",
        item_url="https://example.invalid/item-1",
        owner_ref="owner-1",
        product_grade="A级",
        tags=["主推"],
        strike_price_amount=Decimal("49.99"),
        strike_price_currency_code="USD",
        sale_price_amount=Decimal("39.99"),
        sale_price_currency_code="USD",
        listing_status="在线",
        lifecycle_status="成长期",
        listing_start_at_utc=NOW,
        listing_start_source_raw=None,
        category="家居",
        wfs_available_quantity=Decimal("12"),
        available_quantity=Decimal("2"),
        inbound_quantity=Decimal("4"),
        sales_7d=Decimal("3"),
        sales_14d=Decimal("7"),
        sales_30d=Decimal("15"),
        ad_spend_30d_amount=Decimal("21.50"),
        ad_spend_currency_code="USD",
        buybox_status="拥有",
        walmart_seller="Walmart",
        is_hijacked=False,
        average_rating=Decimal("4.500000"),
        review_count=18,
        brand="SyntheticBrand",
        disabled_reason=None,
        wfs_fee_amount=Decimal("3.50"),
        wfs_fee_currency_code="USD",
        gtin="0085000100001",
        upc="85000100001",
        calculated_at=NOW,
    )


@pytest.mark.parametrize(
    ("hijacked", "expected"),
    [(None, "待确认"), (False, "否"), (True, "是")],
)
def test_listing_csv_preserves_unknown_resell_status(hijacked: bool | None, expected: str) -> None:
    service = ListingManagementService(MagicMock(spec=Session))
    service.tag_repository.tags_for_listing_rows = MagicMock(return_value={})
    service.repository.archive_states_for_listing_rows = MagicMock(return_value={})
    service._to_read = MagicMock(
        return_value=_listing_item().model_copy(update={"is_hijacked": hijacked})
    )
    row = SimpleNamespace(
        id=UUID(int=1), source_account_ref="synthetic-account", item_id="synthetic-item"
    )

    csv_text = service.export_listing_csv(
        ListingManagementQuery(),
        frozenset({"synthetic-account"}),
        columns="is_hijacked",
        _rows=[row],
    )

    assert csv_text.splitlines() == ["是否跟卖", expected]


def test_listing_streaming_export_does_not_truncate_after_ten_thousand_rows() -> None:
    service = ListingManagementService(MagicMock(spec=Session))
    service.tag_repository.tags_for_listing_rows = MagicMock(return_value={})
    service.repository.archive_states_for_listing_rows = MagicMock(return_value={})
    service._to_read = MagicMock(return_value=_listing_item())
    row = SimpleNamespace(
        id=UUID(int=1), source_account_ref="synthetic-account", item_id="synthetic-item"
    )

    def batches():
        for _ in range(20):
            yield [row] * 500
        yield [row]

    service.repository.iter_export_listing_batches = MagicMock(return_value=batches())
    chunks = service.iter_export_listing_csv(
        ListingManagementQuery(),
        frozenset({"synthetic-account"}),
        columns="is_hijacked",
    )

    lines = b"".join(chunks).decode("utf-8-sig").splitlines()
    assert lines[0] == "是否跟卖"
    assert len(lines) == 10_002
    assert lines[-1] == "否"


@pytest.mark.parametrize(
    "untrusted",
    ["=1+1", "+cmd", "-cmd", "@cmd", "\t=cmd", "\r=cmd", "\n=cmd", ["=cmd", "safe"]],
)
def test_listing_csv_escapes_formula_prefix_after_flattening(untrusted: object) -> None:
    rendered = ListingManagementService._csv_value(untrusted)
    assert rendered.startswith("'")
    assert rendered[1:].lstrip()[0] in "=+-@"


def test_openapi_contains_listing_management_route() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/listings/walmart" in paths


def test_listing_multi_select_preserves_commas_unicode_and_quotes() -> None:
    values = ["Synthetic, Store", "合成, 店铺", 'Synthetic "Quoted" Store']
    assert _csv_values(json.dumps(values, ensure_ascii=False)) == values


def test_owner_lookup_uses_latest_source_snapshot_and_keeps_pairing() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("""
            CREATE TABLE dwd_lingxing_sku_product_info_current (
                source_account_ref TEXT, lingxing_sku_code TEXT,
                source_observed_at TIMESTAMP, updated_at TIMESTAMP,
                source_snapshot_id TEXT, owner_uid TEXT, owner_name TEXT,
                product_developer_uid TEXT, product_developer_name TEXT
            )
        """)
        )
        connection.execute(
            text("""
            INSERT INTO dwd_lingxing_sku_product_info_current VALUES
            ('account-a', 'sku-a', '2026-01-01', '2026-01-01', 'snapshot-a',
             'a', 'Old owner', 'a', 'Old developer'),
            ('account-a', 'sku-a', '2026-01-02', '2026-01-02', 'snapshot-b',
             'z', 'New owner', 'z', 'New developer'),
            ('account-b', 'sku-a', '2026-01-03', '2026-01-03', 'snapshot-c',
             'b', 'Other account', 'b', 'Other developer')
        """)
        )
    with Session(engine) as session:
        lookup = ListingManagementRepository(session)._owner_lookup()
        rows = session.execute(lookup.select()).mappings().all()
    assert [
        (row["source_account_ref"], row["owner_name"], row["product_developer_name"])
        for row in rows
    ] == [
        ("account-a", "New owner", "New developer"),
        ("account-b", "Other account", "Other developer"),
    ]


def test_listing_query_reads_raw_start_time_by_stable_business_key() -> None:
    repository = ListingManagementRepository(MagicMock(spec=Session))
    statement = repository._filtered_listing_statement(
        account_refs=frozenset({"synthetic-account"}),
        store_id=None,
        owner_ref="",
        product_type="",
        status="",
        tag="",
        summary_filter="total",
        search_field="sku",
        keyword="",
        batch_values="",
    )

    sql = str(statement.compile())
    assert "LEFT OUTER JOIN dim_walmart_listings" in sql
    assert "dim_walmart_listings.source_account_ref =" in sql
    assert "dim_walmart_listings.store_id =" in sql
    assert "dim_walmart_listings.item_id =" in sql


def test_listing_archive_unknown_is_visible_by_default_but_not_explicitly_active() -> None:
    session = MagicMock(spec=Session)
    repository = ListingManagementRepository(session)
    kwargs = dict(
        account_refs=frozenset({"synthetic-account"}),
        store_id=None,
        owner_ref="",
        product_type="",
        status="",
        tag="",
        summary_filter="total",
        search_field="sku",
        keyword="",
        batch_values="",
    )
    active_sql = str(repository._filtered_listing_statement(**kwargs).compile())
    unknown_sql = str(
        repository._filtered_listing_statement(**kwargs, archive_status="unknown").compile()
    )
    explicit_active_sql = str(
        repository._filtered_listing_statement(**kwargs, archive_status="active").compile()
    )
    assert "listing_archive_states.is_archived IS false" in active_sql
    assert "listing_archive_states.listing_id IS NULL" in active_sql
    assert "listing_archive_states.listing_id IS NULL" not in explicit_active_sql
    assert "listing_archive_states.listing_id IS NULL" in unknown_sql

    session.execute.return_value.mappings.return_value.one.return_value = {
        "active_count": 2,
        "archived_count": 3,
        "unknown_count": 4,
    }
    assert repository.archive_status_filter_options(frozenset({"synthetic-account"})) == [
        {"value": "active", "label": "未归档", "count": 2},
        {"value": "archived", "label": "已归档", "count": 3},
        {"value": "unknown", "label": "状态未确认", "count": 4},
    ]


def test_restored_listing_does_not_expose_stale_archive_reason() -> None:
    service = ListingManagementService(MagicMock(spec=Session))
    listing = SimpleNamespace(**{**_listing_item().model_dump(), "tags_json": []})
    restored = service._to_read(
        listing,
        custom_tags=[],
        is_archived=False,
        archive_state_known=True,
        archive_reason="historical synthetic reason",
    )
    archived = service._to_read(
        listing,
        custom_tags=[],
        is_archived=True,
        archive_state_known=True,
        archive_reason="current synthetic reason",
    )
    assert restored.archive_reason is None
    assert archived.archive_reason == "current synthetic reason"


def test_listing_management_route_fails_closed_for_auth_permission_and_scope() -> None:
    assert TestClient(create_app()).get("/api/listings/walmart").status_code == 401

    denied = TestClient(_app("unrelated:permission")).get("/api/listings/walmart")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    application = create_app()
    application.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="synthetic-user",
        permissions=ALL_PERMISSIONS,
    )
    application.dependency_overrides[get_db_session] = lambda: MagicMock(spec=Session)
    response = TestClient(application).get("/api/listings/walmart")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DATA_SCOPE_DENIED"


def test_listing_management_route_returns_envelope_and_meta(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def list_listings(
        self: ListingManagementService,
        query: Any,
        account_refs: frozenset[str],
    ) -> tuple[ListingManagementListData, int, datetime]:
        captured["query"] = query
        captured["account_refs"] = account_refs
        return ListingManagementListData(items=[_listing_item()]), 1, NOW

    monkeypatch.setattr(ListingManagementService, "list_listings", list_listings)

    response = TestClient(_app()).get(
        "/api/listings/walmart",
        params={
            "search_field": "sku",
            "keyword": "sku-1",
            "page": 2,
            "page_size": 50,
        },
    )

    body = _assert_envelope(response)
    assert captured["account_refs"] == frozenset({"synthetic-account"})
    assert captured["query"].page == 2
    assert captured["query"].page_size == 50
    assert body["data"]["items"][0]["local_sku"] == "sku-1"
    assert body["data"]["items"][0]["sale_price_amount"] == "39.99"
    assert body["data"]["items"][0]["listing_start_source_raw"] is None
    assert body["meta"]["source_objects"] == [
        "mart_listing_management_current",
        "dim_walmart_listings",
    ]
    assert body["meta"]["total"] == 1


def test_listing_view_permission_cannot_modify_account_tags(monkeypatch: Any) -> None:
    create_call = MagicMock(
        return_value=ListingTagRead(
            id="tag-1", source_account_ref="synthetic-account", name="Synthetic", color="blue"
        )
    )
    monkeypatch.setattr(ListingManagementService, "create_tag", create_call)

    denied = TestClient(_app("page:products:listing-management:view")).post(
        "/api/listings/tags",
        json={"name": "Synthetic", "color": "blue"},
    )
    assert denied.status_code == 403
    create_call.assert_not_called()

    allowed = TestClient(_app("action:products:listing-management:manage-tags")).post(
        "/api/listings/tags",
        json={"name": "Synthetic", "color": "blue"},
    )
    assert allowed.status_code == 200
    create_call.assert_called_once()


@pytest.mark.parametrize(
    ("method", "path", "payload", "service_method"),
    [
        (
            "POST",
            "/api/listings/walmart/00000000-0000-0000-0000-000000000003/archive",
            {"reason": "synthetic reason"},
            "archive_listing",
        ),
        (
            "POST",
            "/api/listings/walmart/00000000-0000-0000-0000-000000000003/restore",
            None,
            "restore_listing",
        ),
        (
            "PUT",
            "/api/listings/walmart/00000000-0000-0000-0000-000000000003/gpt-analysis",
            {"keyword_analysis_url": "", "ad_analysis_url": ""},
            "update_gpt_analysis_link",
        ),
        (
            "POST",
            "/api/listings/tags/batch-set",
            {"listing_ids": ["00000000-0000-0000-0000-000000000003"], "mode": "replace"},
            "batch_set_tags",
        ),
        (
            "PATCH",
            "/api/listings/tags/00000000-0000-0000-0000-000000000004",
            {"name": "Synthetic"},
            "update_tag",
        ),
        (
            "DELETE",
            "/api/listings/tags/00000000-0000-0000-0000-000000000004",
            None,
            "delete_tag",
        ),
    ],
)
def test_listing_view_permission_cannot_call_any_write_service(
    monkeypatch: Any,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    service_method: str,
) -> None:
    write_call = MagicMock()
    monkeypatch.setattr(ListingManagementService, service_method, write_call)
    response = TestClient(_app("page:products:listing-management:view")).request(
        method, path, json=payload
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    write_call.assert_not_called()


def test_listing_tag_create_rejects_account_outside_authorized_scope() -> None:
    response = TestClient(_app("action:products:listing-management:manage-tags")).post(
        "/api/listings/tags",
        json={
            "name": "Synthetic",
            "color": "#1677FF",
            "source_account_ref": "synthetic-other-account",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DATA_SCOPE_DENIED"


def test_listing_tag_batch_scope_failure_is_all_or_nothing(monkeypatch: Any) -> None:
    batch_call = MagicMock(side_effect=PermissionError("hidden"))
    monkeypatch.setattr(ListingManagementService, "batch_set_tags", batch_call)
    response = TestClient(_app("action:products:listing-management:manage-tags")).post(
        "/api/listings/tags/batch-set",
        json={
            "listing_ids": ["00000000-0000-0000-0000-000000000001"],
            "tag_values": ["Synthetic"],
            "mode": "append",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DATA_SCOPE_DENIED"

    monkeypatch.setattr(
        ListingManagementService,
        "batch_set_tags",
        lambda _self, **_kwargs: ListingTagBatchSetData(
            updated_listings=1,
            tag_count=1,
            mode="append",
        ),
    )
    allowed = TestClient(_app("action:products:listing-management:manage-tags")).post(
        "/api/listings/tags/batch-set",
        json={
            "listing_ids": ["00000000-0000-0000-0000-000000000001"],
            "tag_values": ["Synthetic"],
            "mode": "append",
        },
    )
    assert allowed.status_code == 200


def test_listing_tag_repository_rejects_mixed_scope_before_any_write() -> None:
    session = MagicMock(spec=Session)
    authorized_id = "00000000-0000-0000-0000-000000000001"
    unauthorized_id = "00000000-0000-0000-0000-000000000002"
    session.execute.return_value.all.return_value = [
        SimpleNamespace(
            id=UUID(authorized_id),
            source_account_ref="synthetic-account",
            item_id="item-1",
        )
    ]

    with pytest.raises(PermissionError):
        ListingTagRepository(session).batch_set_tags(
            account_refs=frozenset({"synthetic-account"}),
            listing_ids=[authorized_id, unauthorized_id],
            tag_ids=[],
            tag_values=["Synthetic"],
            mode="append",
        )

    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize("inactive", [False, True])
def test_listing_tag_batch_rejects_missing_or_inactive_id_before_any_write(
    inactive: bool,
) -> None:
    session = MagicMock(spec=Session)
    listing_id = UUID("00000000-0000-0000-0000-000000000001")
    valid_tag_id = UUID("00000000-0000-0000-0000-000000000011")
    invalid_tag_id = UUID("00000000-0000-0000-0000-000000000012")
    listing_row = namedtuple("ListingRow", "id source_account_ref item_id")
    session.execute.return_value.all.return_value = [
        listing_row(listing_id, "synthetic-account", "synthetic-item")
    ]
    session.scalars.return_value = (
        []
        if inactive
        else [
            ProductCustomTag(
                id=valid_tag_id,
                source_account_ref="synthetic-account",
                name="Synthetic valid",
                color="#1677FF",
                is_active=True,
            )
        ]
    )

    with pytest.raises(ValueError, match="LISTING_TAG_NOT_FOUND_OR_INACTIVE"):
        ListingTagRepository(session).batch_set_tags(
            account_refs=frozenset({"synthetic-account"}),
            listing_ids=[str(listing_id)],
            tag_ids=[str(valid_tag_id), str(invalid_tag_id)],
            tag_values=[],
            mode="replace",
        )

    session.execute.assert_called_once()
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_listing_tag_definition_cannot_cross_account_boundary() -> None:
    session = MagicMock(spec=Session)
    foreign_tag = ProductCustomTag(
        id=UUID("00000000-0000-0000-0000-000000000041"),
        source_account_ref="synthetic-other-account",
        name="Synthetic",
        color="#1677FF",
    )
    session.get.return_value = foreign_tag
    repository = ListingTagRepository(session)

    with pytest.raises(ValueError, match="LISTING_TAG_NOT_FOUND"):
        repository.update_tag(
            tag_id=str(foreign_tag.id),
            account_refs=frozenset({"synthetic-account"}),
            name="changed",
            color=None,
            sort_order=None,
            is_active=None,
        )
    with pytest.raises(ValueError, match="LISTING_TAG_NOT_FOUND"):
        repository.delete_tag(
            tag_id=str(foreign_tag.id),
            account_refs=frozenset({"synthetic-account"}),
        )
    session.commit.assert_not_called()


def test_listing_tag_delete_preserves_assignments_for_audit() -> None:
    tag = ProductCustomTag(
        id=UUID("00000000-0000-0000-0000-000000000051"),
        source_account_ref="synthetic-account",
        name="Synthetic",
        color="#1677FF",
        is_active=True,
    )
    session = MagicMock(spec=Session)
    session.get.return_value = tag
    session.scalar.return_value = 0

    ListingTagRepository(session).delete_tag(
        tag_id=str(tag.id), account_refs=frozenset({"synthetic-account"})
    )

    assert tag.deleted_at is not None
    assert tag.is_active is False
    session.delete.assert_not_called()
    session.execute.assert_not_called()
    session.commit.assert_called_once()


def test_listing_tag_value_reuses_concurrent_same_account_definition() -> None:
    tag = ProductCustomTag(
        id=UUID("00000000-0000-0000-0000-000000000052"),
        source_account_ref="synthetic-account",
        name="Synthetic",
        color="#1677FF",
        is_active=True,
    )
    session = MagicMock(spec=Session)
    session.scalar.side_effect = [None, tag]

    resolved = ListingTagRepository(session)._resolve_tags(
        account_ref="synthetic-account", tag_ids=[], tag_values=["Synthetic"]
    )

    assert resolved == [tag]
    session.execute.assert_called_once()
    session.add.assert_not_called()


def test_listing_tag_list_filters_definitions_by_account() -> None:
    session = MagicMock(spec=Session)
    session.execute.return_value.all.return_value = []
    ListingTagRepository(session).list_tags(account_refs=frozenset({"synthetic-account"}))
    sql = str(session.execute.call_args.args[0])
    assert "product_custom_tags.source_account_ref IN" in sql
    assert (
        "product_custom_tags.source_account_ref = product_custom_tag_assignments.source_account_ref"
    ) in sql


def test_listing_tag_filter_requires_assignment_and_definition_account_match() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = 0
    session.execute.return_value.all.return_value = []

    ListingManagementRepository(session).list_listings(
        account_refs=frozenset({"synthetic-account"}),
        store_id=None,
        search_field="sku",
        keyword="",
        tag='["Synthetic"]',
        page=1,
        page_size=50,
    )

    sql = str(session.execute.call_args.args[0])
    assert (
        "product_custom_tags.source_account_ref = product_custom_tag_assignments.source_account_ref"
    ) in sql


def test_listing_server_sort_uses_monitor_projection() -> None:
    session = MagicMock(spec=Session)
    session.scalar.return_value = 0
    session.execute.return_value.all.return_value = []
    repository = ListingManagementRepository(session)
    for sort_field, expected_order in (
        ("salePrice", "effective_sale_price_amount"),
        ("listPrice", "effective_strike_price_amount"),
        ("rating", "effective_average_rating"),
        ("checkedAt", "monitor_observed_at"),
    ):
        repository.list_listings(
            account_refs=frozenset({"synthetic-account"}),
            store_id=None,
            search_field="sku",
            keyword="",
            page=1,
            page_size=50,
            sort_field=sort_field,
        )
        order_by = str(session.execute.call_args.args[0]).split("ORDER BY")[-1]
        assert expected_order in order_by
        assert "mart_listing_management_current.id ASC" in order_by


def test_listing_post_export_keeps_batch_ids_out_of_url_and_requires_action_permission(
    monkeypatch: Any,
) -> None:
    export = MagicMock(return_value=iter([b"SKU\nSynthetic\n"]))
    monkeypatch.setattr(ListingManagementService, "iter_export_listing_csv", export)
    payload = {
        "filters": {"search_field": "item_id"},
        "batch_values": ["synthetic-item"],
        "selected_ids": ["00000000-0000-0000-0000-000000000003"],
        "columns": ["sku"],
    }
    denied = TestClient(_app("page:products:listing-management:view")).post(
        "/api/listings/walmart/export/search", json=payload
    )
    assert denied.status_code == 403
    export.assert_not_called()

    allowed = TestClient(_app("action:products:listing-management:export")).post(
        "/api/listings/walmart/export/search", json=payload
    )
    assert allowed.status_code == 200
    assert "Synthetic" in allowed.text
    assert export.call_args.args[0].batch_values == '["synthetic-item"]'
    assert export.call_args.kwargs["selected_ids"] == payload["selected_ids"][0]


def test_listing_post_batch_search_validates_up_to_one_thousand_ids() -> None:
    from pydantic import ValidationError

    from app.modules.data_pages.schemas import (
        ListingManagementBatchSearchRequest,
        ListingManagementQuery,
    )

    request = ListingManagementBatchSearchRequest(
        filters=ListingManagementQuery(search_field="item_id"),
        batch_values=[f"{index:011d}" for index in range(1000)],
    )
    assert len(request.batch_values) == 1000
    with pytest.raises(ValidationError):
        ListingManagementBatchSearchRequest(
            filters=ListingManagementQuery(),
            batch_values=[f"{index:011d}" for index in range(1001)],
        )
    with pytest.raises(ValidationError):
        ListingManagementBatchSearchRequest(
            filters=ListingManagementQuery(),
            batch_values=[""],
        )
