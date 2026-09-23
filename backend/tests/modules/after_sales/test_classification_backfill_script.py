from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = BACKEND_ROOT / "scripts" / "backfill_after_sales_classification.py"


def test_classification_backfill_uses_string_refund_item_id() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "where id = :id" in source
    assert "where id = cast(:id as uuid)" not in source
