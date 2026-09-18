from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy.orm import Session

from app.modules.integration_sync.data_pages_real_sync import (
    SP_CAMPAIGN_TYPES,
    DataPagesRealSyncRunner,
    ProviderResponse,
    _ad_identity_hash,
    _resolve_ad_identity,
    _scalar_candidates,
)


class _SequenceClient:
    def __init__(self, responses: list[ProviderResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, parser_key: str, body: dict[str, Any], **kwargs: Any) -> ProviderResponse:
        self.calls.append({"parser_key": parser_key, "body": body, **kwargs})
        return self.responses.pop(0)


def _response(
    *,
    parser_key: str,
    rows: tuple[dict[str, Any], ...] = (),
    code: int = 0,
    total: int | None = None,
    page_no: int = 1,
    page_size: int = 100,
) -> ProviderResponse:
    data: dict[str, Any] = {"list": list(rows)}
    if total is not None:
        data["total"] = total
    return ProviderResponse(
        parser_key=cast(Any, parser_key),
        response_json={"code": code, "data": data},
        rows=rows,
        page_no=page_no,
        page_size=page_size,
        pulled_at=datetime.now(UTC),
        provider_code=code,
        response_code=200,
    )


def _runner(client: _SequenceClient, *, page_size: int = 100) -> DataPagesRealSyncRunner:
    runner = DataPagesRealSyncRunner(
        session=cast(Session, object()),
        client=cast(Any, client),
        source_account_ref="primary",
        business_date=date(2026, 9, 2),
        page_size=page_size,
        campaign_type="SP",
        max_advertisers=10,
    )
    runner.store_ids = ("store-a", "store-b")
    runner._persist_raw_blob = cast(Any, lambda *args, **kwargs: None)
    return runner


def test_sale_stat_real_body_keeps_data_type_one() -> None:
    runner = _runner(_SequenceClient([]))

    body = runner._sale_stat_body(page=2, size=100, result_type=3)

    assert body["data_type"] == 1
    assert body["date_unit"] == "4"
    assert body["result_type"] == "3"
    assert body["page"] == 2


def test_grouped_sale_stat_identity_is_not_silently_collapsed() -> None:
    assert _scalar_candidates(["item-a", "item-b"]) == ["item-a", "item-b"]
    assert _scalar_candidates(["store-a", "store-a"]) == ["store-a"]


def test_ad_identity_uses_seller_store_item_msku_triple() -> None:
    result = _resolve_ad_identity(
        {"mpSellerName": " Seller A "},
        item_id="item-1",
        store_name_map={"seller a": {"store-a"}},
        store_item_map={("store-a", "item-1"): {"msku-a"}},
        item_map={"item-1": {("store-a", "msku-a"), ("store-b", "msku-b")}},
    )

    assert result == ("store-a", "msku-a", "seller_store_item")


def test_ad_identity_only_uses_global_item_fallback_when_unique() -> None:
    unique = _resolve_ad_identity(
        {},
        item_id="item-1",
        store_name_map={},
        store_item_map={},
        item_map={"item-1": {("store-a", "msku-a")}},
    )
    ambiguous = _resolve_ad_identity(
        {},
        item_id="item-2",
        store_name_map={},
        store_item_map={},
        item_map={
            "item-2": {
                ("store-a", "msku-a"),
                ("store-b", "msku-b"),
            }
        },
    )

    assert unique == ("store-a", "msku-a", "unique_item_store_msku")
    assert ambiguous == (None, None, None)


def test_return_provider_403_is_recorded_and_does_not_block_other_syncs() -> None:
    client = _SequenceClient([_response(parser_key="walmart_return_order_list", code=403)])
    runner = _runner(client)

    rows = runner._fetch_return_all()

    assert rows == []
    assert runner.summary.return_permission_403 is True
    assert "walmartReturnOrderList:provider_permission_403" in runner.summary.skipped_interfaces
    assert len(client.calls) == 1


def test_ads_ignore_unreliable_total_and_stop_on_short_page() -> None:
    full_page = tuple({"itemId": f"item-{index}"} for index in range(2))
    short_page = ({"itemId": "item-last"},)
    client = _SequenceClient(
        [
            _response(
                parser_key="walmart_ad_item_sp_list",
                rows=full_page,
                total=0,
                page_no=1,
                page_size=2,
            ),
            _response(
                parser_key="walmart_ad_item_sp_list",
                rows=short_page,
                total=0,
                page_no=2,
                page_size=2,
            ),
        ]
    )
    runner = _runner(client, page_size=2)

    rows = runner._fetch_ads_all("123")

    assert len(rows) == 3
    assert len(client.calls) == 2
    assert client.calls[0]["body"]["pageNum"] == 1
    assert client.calls[1]["body"]["pageNum"] == 2


def test_sp_campaign_types_include_manual_auto_sba_and_video() -> None:
    assert SP_CAMPAIGN_TYPES == (
        "sponsoredProducts-manual",
        "sponsoredProducts-auto",
        "sba",
        "video",
    )


def test_ad_identity_hash_ignores_mutable_metrics() -> None:
    original = {
        "key": "stable-provider-key",
        "adSpend": "10.00",
        "numAdsClicks": 3,
    }
    refreshed = {
        "key": "stable-provider-key",
        "adSpend": "8.50",
        "numAdsClicks": 9,
    }

    assert _ad_identity_hash(original) == _ad_identity_hash(refreshed)
