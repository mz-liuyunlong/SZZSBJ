def register_productlist_sync_models() -> None:
    """Register ProductList ORM metadata; these imports are not business dependencies."""
    import app.modules.integration_sync.models  # noqa: F401
    import app.modules.media_assets.models  # noqa: F401
    import app.modules.product_management.models  # noqa: F401
    import app.modules.products.models  # noqa: F401
    import app.modules.sku_detail.models  # noqa: F401
    import app.modules.warehouse_wfs.models  # noqa: F401
