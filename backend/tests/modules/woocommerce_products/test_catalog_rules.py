# Synthetic unit tests for real module logic; no DB or network.
from datetime import UTC
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from app.modules.woocommerce_config.service import WooCommerceConfigError
from app.modules.woocommerce_products import catalog
from app.modules.woocommerce_products.service import RuleWrite, bullets


def sample(i=1):
    return {
        "id": i,
        "name": "Sample",
        "price": "21.99",
        "stock_quantity": None,
        "manage_stock": False,
        "stock_status": "instock",
        "status": "publish",
        "sku": "",
        "date_created_gmt": "2026-11-17T00:00:00",
        "images": [{"id": 2, "src": "https://example.com/image.jpg"}],
        "brands": [{"id": 22, "name": "Rinima"}],
        "categories": [{"id": 21, "name": "Rinima"}],
        "permalink": "https://example.com/product/test",
        "meta_data": [{"key": "token", "value": "never persist"}],
        "post_password": "excluded",
    }


def test_normalization_preserves_unknown_stock_and_date():
    evidence, values = catalog.normalize_product(sample(), "USD")
    assert values["stock_quantity"] is None
    assert values["sku"] is None
    assert values["price"] == Decimal("21.99")
    assert values["source_created_at"].tzinfo == UTC
    assert "published_at" not in values
    assert "meta_data" not in evidence and "post_password" not in evidence
    assert values["image_urls"] == ["https://example.com/image.jpg"]


def test_pagination_all_pages():
    def fake(host, addresses, key, secret, path):
        if "settings/" in path:
            return {"value": "USD"}, None, None
        page = int(parse_qs(urlsplit(path).query)["page"][0])
        return ([sample(i) for i in (range(1, 21) if page == 1 else [21])], "21", "2")

    with (
        patch.object(catalog, "_resolve_public_ips", return_value=["8.8.8.8"]),
        patch.object(catalog, "request_json", side_effect=fake),
    ):
        c, rows = catalog.fetch_catalog("https://example.com", "synthetic-key", "synthetic-secret")
    assert c == "USD" and len(rows) == 21


def test_duplicate_page_rejected():
    with (
        patch.object(catalog, "_resolve_public_ips", return_value=["8.8.8.8"]),
        patch.object(
            catalog,
            "request_json",
            side_effect=[
                ({"value": "USD"}, None, None),
                ([sample() for _ in range(20)], "20", "1"),
            ],
        ),
    ):
        with pytest.raises(WooCommerceConfigError, match="DUPLICATE"):
            catalog.fetch_catalog("https://example.com", "synthetic-key", "synthetic-secret")


def test_unknown_currency_rejected():
    with (
        patch.object(catalog, "_resolve_public_ips", return_value=["8.8.8.8"]),
        patch.object(catalog, "request_json", return_value=({"value": ""}, None, None)),
    ):
        with pytest.raises(WooCommerceConfigError, match="CURRENCY"):
            catalog.fetch_catalog("https://example.com", "synthetic-key", "synthetic-secret")


def test_submission_id_string_and_defaults():
    rule = RuleWrite(
        version=0,
        mappings=[],
        submission_stores=[
            {"source_account_ref": "A", "source_store_id": "S", "submission_store_id": "000123"}
        ],
    )
    assert rule.submission_stores[0].submission_store_id == "000123"
    assert rule.submission_interval_days == 60 and rule.price_markup == Decimal(2)
    assert rule.auto_publish_enabled is False


def test_bullets_only_actual_list_items():
    assert bullets("<ul><li>first</li><li>second &amp; third</li></ul>") == [
        "first",
        "second & third",
    ]
    assert bullets("<p>normal description</p>") == []
