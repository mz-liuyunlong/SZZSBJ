def register_productlist_sync_models() -> None:
    """Register ProductList ORM metadata; these imports are not business dependencies."""
    import app.modules.integration_sync.models
    import app.modules.media_assets.models
    import app.modules.operation_plans.models
    import app.modules.pmc_domestic.inbound_models
    import app.modules.pmc_domestic.models
    import app.modules.pmc_domestic.packing_models
    import app.modules.pmc_domestic.packing_stock_models
    import app.modules.pmc_domestic.warehouse_models
    import app.modules.pmc_purchase.gate3_models
    import app.modules.pmc_purchase.models
    import app.modules.pmc_wfs.models
    import app.modules.pmc_wfs.creation_models
    import app.modules.pmc_wfs.exception_models
    import app.modules.product_management.models
    import app.modules.products.models
    import app.modules.sku_detail.models
    import app.modules.walmart_remote.models
    import app.modules.warehouse_wfs.models  # noqa: F401
