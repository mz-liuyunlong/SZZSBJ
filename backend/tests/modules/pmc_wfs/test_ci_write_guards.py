"""The CI-only guard exception in conftest.py stays exactly one database wide, and the real
app guards still refuse that database (no database needed; runs everywhere)."""

from types import SimpleNamespace

import pytest
from sqlalchemy.engine import make_url

from app.core.api import ApiError
from app.modules.pmc_domestic.packing_service import database_write_allowed
from app.modules.pmc_wfs import creation_service
from app.modules.pmc_wfs.creation_service import guard_write
from tests.modules.pmc_wfs.schema_support import is_ci_write_target

# Bound at import, before any per-test patch: these are the real guard functions.
CI = make_url(
    "postgresql+psycopg://wfs_integration_ci:local_ci_only@127.0.0.1:5432/wfs_integration_ci"
)


def _session(url):
    return SimpleNamespace(get_bind=lambda: SimpleNamespace(url=url))


def test_real_guards_still_refuse_the_ci_database(monkeypatch):
    assert not database_write_allowed("test", CI)
    assert not database_write_allowed("local", CI)
    monkeypatch.setattr(
        creation_service,
        "get_settings",
        lambda: SimpleNamespace(app_env=SimpleNamespace(value="test")),
    )
    with pytest.raises(ApiError, match="WFS_ISOLATED_TEST_DATABASE_REQUIRED"):
        guard_write(_session(CI))


def test_ci_exception_matches_exactly_one_target():
    assert is_ci_write_target("test", CI)
    for env in ("local", "production", "staging"):
        assert not is_ci_write_target(env, CI)
    for other in (
        CI.set(port=55432),
        CI.set(host="localhost"),
        CI.set(host="10.0.0.5"),
        CI.set(database="wfs_integration_ci2"),
        CI.set(database="postgres"),
        CI.set(drivername="postgresql+psycopg2"),
        CI.update_query_dict({"sslmode": "disable"}),
    ):
        assert not is_ci_write_target("test", other), other.render_as_string(hide_password=True)
