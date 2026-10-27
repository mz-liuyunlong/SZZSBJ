"""Internal purchase orchestration identity; never an outbound Lingxing endpoint."""

PURCHASE_PIPELINE_KEY = "pmcPurchaseBoardSync"
PURCHASE_PIPELINE_HANDLER = "pmc.purchase_board.pipeline.v1"
PURCHASE_PIPELINE_PATH = "/internal/pmc-purchase-board-sync"
PURCHASE_PIPELINE_CRON = "0 */3 * * *"
PURCHASE_SOURCE_KEYS = ("purchasePlanList", "purchaseOrderList", "purchaseReceiptOrderList")
