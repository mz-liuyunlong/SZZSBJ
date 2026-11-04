"""WFS integration tests in the CI job only: let the two app write guards accept the job's
own throwaway database, and nothing else.

``APP_ENV=test`` in CI. The app guards only accept the local developer / isolated test
databases (``creation_service.guard_write``: ``wfs_v2_test_*``;
``packing_service.database_write_allowed``: the local test database on port 55432), so the
CI database ``127.0.0.1:5432/wfs_integration_ci`` is refused. When — and only when —
``WFS_CI_DATABASE_URL`` is set (``integration_target()`` re-validates that it is inside
GitHub Actions and points at exactly that database), each test gets wrappers that return
early for that exact target and otherwise call the real guard. Locally (no
``WFS_CI_DATABASE_URL``) nothing is patched. The real guards are unchanged and are still
asserted in ``test_ci_write_guards.py``. Same idea as
``tests/db/test_packing_pending_edit_postgresql.py`` (``service.guard_local = lambda: None``
for its disposable CI database), but scoped to one URL instead of disabled.
"""

import os

import pytest

from app.core.config import get_settings
from app.modules.pmc_domestic import packing_service
from app.modules.pmc_wfs import creation_service, creation_worker
from tests.modules.pmc_wfs.schema_support import integration_target, is_ci_write_target


@pytest.fixture(autouse=True)
def ci_database_write_guards(monkeypatch):
    if not os.environ.get("WFS_CI_DATABASE_URL"):
        yield
        return
    integration_target()  # raises unless inside GitHub Actions and the exact CI URL
    real_allowed = packing_service.database_write_allowed
    real_guard = creation_service.guard_write

    def database_write_allowed(env, url):
        return is_ci_write_target(env, url) or real_allowed(env, url)

    def guard_write(session):
        if is_ci_write_target(get_settings().app_env.value, session.get_bind().url):
            return
        real_guard(session)

    monkeypatch.setattr(packing_service, "database_write_allowed", database_write_allowed)
    # creation_worker imported guard_write by name; patch both bindings.
    monkeypatch.setattr(creation_service, "guard_write", guard_write)
    monkeypatch.setattr(creation_worker, "guard_write", guard_write)
    yield
