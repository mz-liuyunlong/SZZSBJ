"""Preflight for start-local-api.ps1: local APP_ENV and isolated dev database only."""

from __future__ import annotations

import os
import sys

from sqlalchemy.engine import make_url


def main() -> None:
    url = make_url(os.environ["DATABASE_URL"])
    ok = (
        os.environ.get("APP_ENV") == "local"
        and url.drivername == "postgresql+psycopg"
        and url.host == "127.0.0.1"
        and url.port == 55432
        and url.database == "szzsbj_dev"
        and not url.query
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
