"""Additional read-only operations catalog tests."""

from app.integrations.walmart.operations_catalog import operations_read_registry


def test_shipping_reads_are_registered() -> None:
    registry = operations_read_registry(
        approved_keys=frozenset({"shipping_settings_get", "shipping_carriers_list"})
    )
    assert registry.prepare("shipping_settings_get").path == "/v3/settings/shipping"
    assert registry.prepare("shipping_carriers_list").path == "/v3/shipping/labels/carriers"
