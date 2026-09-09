from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_alembic_scaffold_loads_offline_without_revisions() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    assert config.get_main_option("sqlalchemy.url") is None
    assert script.get_heads() == []
    assert not list((BACKEND_ROOT / "alembic" / "versions").glob("*.py"))
