from decimal import Decimal

from app.modules.after_sales.service import AfterSalesRefundService


def _service() -> AfterSalesRefundService:
    return AfterSalesRefundService(None)  # type: ignore[arg-type]


def test_item_read_preserves_raw_reason_and_returns_colored_standard_tags() -> None:
    item = _service()._item_read(  # noqa: SLF001
        {
            "id": "row-1",
            "store_id": "store-a",
            "store_name": "Store A",
            "owner_ref": "owner-a",
            "item_id": "item-a",
            "product_name": "Product A",
            "local_sku": "SKU-A",
            "msku": "MSKU-A",
            "return_order_id": "return-a",
            "customer_order_id": "customer-a",
            "purchase_order_id": "purchase-a",
            "platform_order_id": "purchase-a",
            "purchase_time_at": None,
            "refund_time_at": None,
            "refund_lag_days": None,
            "return_qty": Decimal("1"),
            "refund_amount": Decimal("19.99"),
            "refund_currency_code": "USD",
            "refund_loss_amount": Decimal("10.25"),
            "return_reason_code": "Other",
            "return_description": "Shipping box damaged",
            "reason_code": "SHIPPING_BOX_DAMAGED",
            "reason_name": "运输箱破损",
            "reason_category_code": "LOGISTICS",
            "reason_category_name": "物流问题",
            "reason_color": "#1677FF",
            "responsibility_code": "LOGISTICS",
            "responsibility_name": "物流问题",
            "responsibility_color": "#1677FF",
            "responsibility_source": "EXACT_PAIR",
            "responsibility_confidence": "HIGH",
            "current_refund_status": "REFUND_COMPLETED",
            "refund_completed": True,
        }
    )

    assert item.return_reason_code == "Other"
    assert item.return_description == "Shipping box damaged"
    assert item.reason.code == "SHIPPING_BOX_DAMAGED"
    assert item.reason.name == "运输箱破损"
    assert item.reason.color == "#1677FF"
    assert item.responsibility.code == "LOGISTICS"
    assert item.responsibility.source == "EXACT_PAIR"
    assert item.responsibility.confidence == "HIGH"


def test_product_read_exposes_dominant_reason_and_responsibility_tags() -> None:
    product = _service()._product_read(  # noqa: SLF001
        {
            "product_key": '["store-a", "item-a", "msku-a"]',
            "store_id": "store-a",
            "store_name": "Store A",
            "local_sku": "SKU-A",
            "msku": "MSKU-A",
            "item_id": "item-a",
            "product_name": "Product A",
            "owner_ref": "owner-a",
            "refund_orders": 2,
            "refund_qty": Decimal("3"),
            "refund_amount": Decimal("60"),
            "refund_loss_amount": Decimal("30"),
            "sales_qty": Decimal("20"),
            "refund_rate": Decimal("15"),
            "top_reason_code": "PRODUCT_DEFECTIVE",
            "top_reason_name": "商品故障/损坏",
            "top_reason_category_code": "PRODUCT_QUALITY",
            "top_reason_category_name": "商品质量",
            "top_reason_color": "#FF4D4F",
            "top_responsibility_code": "PRODUCT",
            "top_responsibility_name": "商品问题",
            "top_responsibility_color": "#FF4D4F",
        }
    )

    assert product.top_reason is not None
    assert product.top_reason.code == "PRODUCT_DEFECTIVE"
    assert product.top_reason.color == "#FF4D4F"
    assert product.top_responsibility is not None
    assert product.top_responsibility.code == "PRODUCT"
    assert product.top_responsibility.name == "商品问题"
