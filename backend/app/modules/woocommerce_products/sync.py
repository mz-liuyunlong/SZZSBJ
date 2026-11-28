"""Explicit operator entrypoint. No scheduler or production authorization implied."""

import argparse
import json
from uuid import UUID

import sqlalchemy as sa

from app.core.config import AppEnvironment, get_database_url, get_settings
from app.db.session import get_session_factory
from app.modules.woocommerce_config.models import WooCommerceStore
from app.modules.woocommerce_config.service import WooCommerceConfigError

from .catalog import sync_store


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--list-stores", action="store_true")
    modes.add_argument("--store-id", type=UUID)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--production-approved",
        action="store_true",
        help="Only use after separately authorized production synchronization",
    )
    args = parser.parse_args()
    cfg = get_settings()
    url = get_database_url(cfg)
    # Local never means a production tunnel or hybrid. Production requires an
    # explicit separate operator acknowledgement and the configured app database.
    if cfg.app_env is AppEnvironment.LOCAL:
        if (
            args.production_approved
            or url.host not in ("127.0.0.1", "localhost", "::1")
            or url.port != 55433
            or url.query
        ):
            raise SystemExit("STOP=NOT_VERIFIED_LOCAL_DATABASE")
    elif cfg.app_env is AppEnvironment.PRODUCTION:
        if not args.production_approved or url.database != "szzsbj_app":
            raise SystemExit("STOP=PRODUCTION_SYNC_REQUIRES_SEPARATE_AUTHORIZATION")
    else:
        raise SystemExit("STOP=UNSUPPORTED_SYNC_ENVIRONMENT")
    with get_session_factory()() as session:
        if session.execute(sa.text("SHOW transaction_read_only")).scalar_one() != "off":
            raise SystemExit("STOP=READ_ONLY_DATABASE")
        if (
            session.execute(sa.text("SELECT to_regclass('dim_woocommerce_products')")).scalar_one()
            is None
        ):
            raise SystemExit("STOP=WOO_SCHEMA_NOT_INSTALLED")
        store = WooCommerceStore.__table__
        if args.list_stores:
            for r in session.execute(
                sa.select(store.c.id, store.c.name, store.c.enabled, store.c.last_test_ok)
            ).mappings():
                print(json.dumps(dict(r), default=str, ensure_ascii=False))
            return
    if not args.apply:
        raise SystemExit("STOP=EXPLICIT_APPLY_REQUIRED")
    try:
        result = sync_store(
            args.store_id,
            actor="production-manual-sync"
            if cfg.app_env is AppEnvironment.PRODUCTION
            else "local-manual-sync",
        )
    except WooCommerceConfigError as exc:
        raise SystemExit("STOP=" + exc.code) from None
    except Exception as exc:
        # Never print SQL parameter details or credentials.
        raise SystemExit("STOP=WOO_SYNC_FAILED:" + type(exc).__name__) from None
    print(json.dumps(result, ensure_ascii=False))
    print("WOO_PRODUCT_SYNC=PASS")


if __name__ == "__main__":
    main()
