import os
from logging.config import fileConfig

from alembic.ddl.postgresql import PostgresqlImpl
from sqlalchemy import Column, MetaData, PrimaryKeyConstraint, String, Table, create_engine, pool
from sqlalchemy.engine import URL, Connection

import app.models.raw_lingxing_api  # noqa: F401  # Register approved RAW metadata.
import app.modules.data_pages.business_models  # noqa: F401  # Register sample/refund business models.
import app.modules.data_pages.models  # noqa: F401  # Register DATA-PAGES DIM/FACT/MART.
import app.modules.integration_sync.models  # noqa: F401  # Register sync governance/ODS.
import app.modules.keyword_planning.models  # noqa: F401
import app.modules.listing_rule_config.models  # noqa: F401  # Register Listing rule metadata.
import app.modules.pmc_domestic.inbound_models  # noqa: F401
import app.modules.pmc_domestic.models  # noqa: F401  # Register domestic warehouse tables.
import app.modules.pmc_domestic.packing_models  # noqa: F401
import app.modules.pmc_domestic.packing_stock_models  # noqa: F401
import app.modules.pmc_domestic.warehouse_models  # noqa: F401
import app.modules.pmc_purchase.gate3_models  # noqa: F401  # Register PMC purchase Gate 3.
import app.modules.pmc_purchase.models  # noqa: F401  # Register PMC purchase ODS.
import app.modules.pmc_wfs.models  # noqa: F401  # Pending drafts; local additive setup approved.
import app.modules.pmc_wfs.creation_models  # noqa: F401  # V2 count-based operations.
import app.modules.product_management.models  # noqa: F401  # Register product management BFF.
import app.modules.products.models  # noqa: F401  # Register approved model metadata.
import app.modules.sku_detail.models  # noqa: F401  # Register SKU DWD/DWS projections.
import app.modules.walmart_monitor.models  # noqa: F401  # Register monitor RAW events.
from alembic import context
from app.core.config import AppEnvironment, SettingsError, get_database_url, get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


class ProjectPostgresqlImpl(PostgresqlImpl):
    """Create a version table that can hold the repository's historical revision ids."""

    __dialect__ = "postgresql"

    def version_table_impl(
        self,
        *,
        version_table: str,
        version_table_schema: str | None,
        version_table_pk: bool,
        **_kwargs: object,
    ) -> Table:
        table = Table(
            version_table,
            MetaData(),
            Column("version_num", String(128), nullable=False),
            schema=version_table_schema,
        )
        if version_table_pk:
            table.append_constraint(
                PrimaryKeyConstraint("version_num", name=f"{version_table}_pkc")
            )
        return table


def migration_url() -> URL:
    settings = get_settings()
    production_authorized = os.getenv("PRODUCTION_MIGRATIONS_AUTHORIZED", "").casefold() == "true"
    if settings.app_env is AppEnvironment.PRODUCTION and not production_authorized:
        raise SettingsError("Production migrations require separate authorization")
    return get_database_url(settings)


def run_migrations_offline() -> None:
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        migration_url(),
        poolclass=pool.NullPool,
        hide_parameters=True,
    )
    try:
        with connectable.connect() as connection:
            run_migrations(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
