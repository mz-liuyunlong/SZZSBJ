from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_alembic_scaffold_loads_offline_with_current_revision_chain() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    assert config.get_main_option("sqlalchemy.url") is None
    assert script.get_heads() == ["20260912_0006"]
    revisions = {path.name for path in (BACKEND_ROOT / "alembic" / "versions").glob("*.py")}
    assert {
        "20260912_0003_add_integration_governance.py",
        "20260912_0004_add_integration_ods.py",
        "20260912_0005_add_lingxing_sku_dwd.py",
        "20260912_0006_add_sku_dws.py",
    } <= revisions

    revision = (
        BACKEND_ROOT / "alembic" / "versions" / "20260910_0002_add_raw_lingxing_api.py"
    ).read_text()
    assert revision.count('name=op.f("ck_raw_lingxing_api_api_path")') == 1
    assert '"ix_raw_lingxing_api_raw_hash"' in revision
    assert '"ix_raw_lingxing_api_object_type"' not in revision
