"""Synthetic scope, current ownership, option coverage and route regression checks."""

import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, get_optional_principal
from app.db.session import get_db_session
from app.main import create_app
from app.modules.data_pages.models import LingxingStoreDimension as Store
from app.modules.integration_sync.dependencies import require_source_account_scope
from app.modules.pmc_domestic.inbound_schemas import (
    InboundFilter,
    InboundOptionsQuery,
    InboundQuery,
)
from app.modules.pmc_domestic.inbound_service import InboundReadService
from app.modules.sku_detail.models import LingxingSkuIdentity as Identity
from app.modules.sku_detail.models import LingxingSkuProductInfoCurrent as Info
from tests.modules.pmc_domestic.test_inbound_board import (
    NOW,
    PREFIX,
    READ,
    batch,
    build,
    save,
)
from tests.modules.pmc_domestic.test_inbound_board import session as session
from tests.modules.pmc_domestic.test_read_service import _owner

SCOPE = frozenset({"account"})


@pytest.fixture
def seeded(session):
    connection = session.connection().connection.driver_connection
    connection.create_function("char_length", 1, len)
    for model in (Store, Identity, Info):
        model.__table__.create(session.bind)
    save(session, build(events=[], batches=[batch(store_id="old")]))
    rows = build(
        events=[],
        batches=[
            batch(
                batch_no=f"B{i}",
                order_sn=f"IB{i}",
                sku=f"SKU{i}",
                store_id="001" if i == 1 else "002",
                balance_num=i,
            )
            for i in range(1, 54)
        ],
    )
    save(session, rows)
    save(session, build(events=[], batches=[batch(store_id="secret")]), account="other")
    _owner(session, "SKU1", "0001", "同名负责人", account="account")
    _owner(session, "SKU53", "0002", "同名负责人", account="account")
    _owner(session, "SKU2", "ambiguous-a", account="account")
    _owner(session, "SKU2", "ambiguous-b", account="account")
    _owner(session, "SKU1", "inactive", account="account", active=False)
    _owner(session, "SKU1", "secret-owner", account="other")
    session.add_all(
        [
            Store(
                source_account_ref="account",
                platform_code_raw="walmart",
                store_id="001",
                store_name="惠州店",
                synced_at=NOW,
            ),
            Store(
                source_account_ref="other",
                platform_code_raw="walmart",
                store_id="001",
                store_name="其他账号店名",
                synced_at=NOW,
            ),
        ]
    )
    session.commit()
    return session


def test_options_cover_all_current_rows_and_exclude_wrong_scope_and_ambiguous_owners(seeded):
    service = InboundReadService(seeded, NOW)
    data, meta = service.filter_options(InboundOptionsQuery(), SCOPE)
    assert [x.model_dump() for x in data.stores] == [
        {"value": "001", "label": "惠州店"},
        {"value": "002", "label": "002"},
    ]
    assert [x.value for x in data.owners] == ["0001", "0002"]
    assert [x.label for x in data.owners] == ["同名负责人", "同名负责人"]
    assert service.list(InboundQuery(page_size=1), SCOPE)[0].total == 53
    assert len(data.owners) == 2  # SKU53 is outside the first page, but its owner is available.
    assert {s.value for s in data.statuses} == {
        "in_stock",
        "approved",
        "packed",
        "overdue",
        "shipped",
        "other_out",
    }
    assert all(s.disabled and s.reason for s in data.statuses)
    assert "dwd_lingxing_sku_product_info_current" in meta.source_objects
    assert "dim_lingxing_stores" in meta.source_objects
    for scope, warehouses in ((frozenset(), []), (SCOPE, ["no-access-warehouse"])):
        empty, _ = InboundReadService(seeded, NOW).filter_options(
            InboundOptionsQuery(warehouse_id=warehouses),
            scope,
        )
        assert not empty.stores and not empty.owners


def test_owner_filter_applies_to_list_and_summary_with_store_intersection(seeded):
    service = InboundReadService(seeded, NOW)
    filters = {"owner_uid": ["0001", "0002"]}
    data, meta = service.list(InboundQuery(**filters), SCOPE)
    summary, _ = service.summary(InboundFilter(**filters), SCOPE)
    assert data.total == summary.board_row_count == 2
    assert summary.balance_qty == 54
    assert {r.sku for r in data.items} == {"SKU1", "SKU53"}
    assert "dwd_lingxing_sku_identity_index" in meta.source_objects
    assert service.list(InboundQuery(**filters, store_id=["001"]), SCOPE)[0].total == 1
    for uid in ("ambiguous-a", "ambiguous-b", "secret-owner", "inactive"):
        assert service.list(InboundQuery(owner_uid=[uid]), SCOPE)[0].total == 0


def test_store_conflicting_names_fall_back_to_id_without_changing_counts(seeded):
    seeded.add(
        Store(
            source_account_ref="account",
            platform_code_raw="amazon",
            store_id="001",
            store_name="冲突名称",
            synced_at=NOW,
        )
    )
    seeded.commit()
    service = InboundReadService(seeded, NOW)
    data, _ = service.filter_options(InboundOptionsQuery(), SCOPE)
    assert data.stores[0].label == "001"
    assert service.list(InboundQuery(store_id=["001"]), SCOPE)[0].total == 1


def test_options_route_permissions_scope_and_invalid_filters(monkeypatch):
    app = create_app()
    url = PREFIX + "/filter-options"
    assert url in app.openapi()["paths"]
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_optional_principal] = lambda: None
    client = TestClient(app)
    assert client.get(url).status_code == 401
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="test", permissions=frozenset()
    )
    assert client.get(url).status_code == 403
    app.dependency_overrides[get_optional_principal] = lambda: Principal(
        user_id="test", permissions=frozenset({READ})
    )
    app.dependency_overrides[require_source_account_scope] = lambda: SCOPE

    def options(self, query, accounts):
        from app.modules.pmc_domestic.inbound_schemas import InboundMeta, InboundOptions

        assert accounts == SCOPE and query.warehouse_id == ["WH1"]
        return InboundOptions(stores=[], owners=[], statuses=[]), InboundMeta(
            data_status="not_published", as_of=NOW.date()
        )

    monkeypatch.setattr(InboundReadService, "filter_options", options)
    response = client.get(url, params={"warehouse_id": "WH1"})
    assert (
        response.status_code == 200
        and response.json()["data"]["owner_basis"] == "current_product_owner"
    )
    assert client.get(url, params={"store_id": "001"}).status_code == 422
    assert client.get(url, params={"warehouse_id": " "}).status_code == 422
    for path in (PREFIX, PREFIX + "/summary"):
        for values in ([" "], ["x" * 256], [str(i) for i in range(51)]):
            assert client.get(path, params=[("owner_uid", v) for v in values]).status_code == 422
        assert client.get(path, params={"business_status": "shipped"}).status_code == 422
