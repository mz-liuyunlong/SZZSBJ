"""Frontend page declarations must resolve to backend-registered permission keys.

Hidden and disabled navigation entries are not grantable; if they become active
their permission keys must be registered in the shared IAM catalog.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.modules.iam.permission_catalog_v2 import PERMISSION_KEYS

NAVIGATION = Path(__file__).resolve().parents[4] / "frontend" / "src" / "config" / "navigation.ts"
PAGE = re.compile(r"\bpage\('([^']+)', '([^']+)',")
VIEW = re.compile(r"viewPermissionKey:\s*'([^']+)'")
STATUS = re.compile(r"status:\s*'(disabled|hidden)'")


# The backend page catalog remains the permission authority. The navigation
# is read-only input for an automated drift check; never execute TypeScript.
def test_active_navigation_pages_have_registered_backend_permissions() -> None:
    source = NAVIGATION.read_text(encoding="utf-8")
    matches = list(PAGE.finditer(source))
    assert len(matches) >= 90, "Navigation parser stopped discovering pages"
    missing: list[str] = []
    for index, match in enumerate(matches):
        group_key, local_key = match.groups()
        after = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        details = source[match.end() : after]
        if STATUS.search(details):
            continue
        override = VIEW.search(details)
        required_key = (
            override.group(1)
            if override
            else "page:" + group_key.replace("_", "-") + ":" + local_key.replace("_", "-") + ":view"
        )
        if required_key not in PERMISSION_KEYS:
            missing.append(f"{group_key}_{local_key}: {required_key}")
    assert not missing, "Frontend pages missing IAM grants:\n" + "\n".join(missing)
