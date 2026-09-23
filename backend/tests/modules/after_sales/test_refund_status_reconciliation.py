from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]

FORMAL_IMPORTER = (
    BACKEND_ROOT
    / "scripts"
    / "import_after_sales_refund_items.py"
)

SNAPSHOT_IMPORTER = (
    BACKEND_ROOT
    / "scripts"
    / "import_walmart_return_orders_snapshot.py"
)


def test_formal_importer_reconciles_excluded_refund_statuses() -> None:
    source = FORMAL_IMPORTER.read_text(
        encoding="utf-8"
    )

    assert (
        'EXCLUDED_REFUND_STATUSES = '
        'frozenset({"NOT_REFUNDED", "CANCELLED"})'
        in source
    )

    assert "def collect_excluded_item_keys(" in source
    assert "def delete_excluded_rows(" in source

    assert (
        "delete from after_sales_refund_items"
        in source
    )

    assert (
        "source_account_ref = :source_account_ref"
        in source
    )

    assert (
        "platform_code = :platform_code"
        in source
    )

    assert (
        "return_order_id = :return_order_id"
        in source
    )

    assert (
        "item_index = :item_index"
        in source
    )

    assert (
        "excluded_item_keys = "
        "collect_excluded_item_keys(payload)"
        in source
    )

    assert source.count(
        "delete_excluded_rows("
    ) == 2


def test_snapshot_importer_reconciles_excluded_refund_statuses() -> None:
    source = SNAPSHOT_IMPORTER.read_text(
        encoding="utf-8"
    )

    assert (
        'EXCLUDED_REFUND_STATUSES = '
        'frozenset({"NOT_REFUNDED", "CANCELLED"})'
        in source
    )

    excluded_branch = source.index(
        "if current_refund_status "
        "in EXCLUDED_REFUND_STATUSES:"
    )

    delete_statement = source.index(
        "delete from after_sales_refund_items",
        excluded_branch,
    )

    continue_statement = source.index(
        "continue",
        delete_statement,
    )

    assert (
        excluded_branch
        < delete_statement
        < continue_statement
    )

    delete_block = source[
        delete_statement:continue_statement
    ]

    assert (
        "source_account_ref = :source_account_ref"
        in delete_block
    )

    assert (
        "platform_code = :platform_code"
        in delete_block
    )

    assert (
        "return_order_id = :return_order_id"
        in delete_block
    )

    assert (
        "item_index = :item_index"
        in delete_block
    )


def test_formal_importer_uses_return_order_date_for_refund_and_loss() -> None:
    source = FORMAL_IMPORTER.read_text(
        encoding="utf-8"
    )

    assert "effective_at = (" not in source

    assert (
        "return_order_at.date()"
        in source
    )

    assert (
        "refund_loss_date = refund_effective_date"
        in source
    )


def test_snapshot_importer_persists_refund_loss_effective_state() -> None:
    source = SNAPSHOT_IMPORTER.read_text(
        encoding="utf-8"
    )

    assert (
        '"refund_loss_effective": True'
        in source
    )

    assert (
        '"refund_loss_date": refund_effective_date'
        in source
    )

    assert (
        ":refund_loss_effective"
        in source
    )

    assert (
        ":refund_loss_date"
        in source
    )

    assert (
        "refund_loss_effective = "
        "excluded.refund_loss_effective"
        in source
    )

    assert (
        "refund_loss_date = "
        "excluded.refund_loss_date"
        in source
    )
