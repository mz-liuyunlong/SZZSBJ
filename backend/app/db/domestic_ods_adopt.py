"""Adopt or create the four domestic warehouse ODS tables.

Fresh environments: create tables, constraints and indexes from ORM metadata.
Existing environments (e.g. production tables created from
``docs/delivery/domestic-warehouse-ods-tables.sql``): verify column nullability,
varchar length, and PostgreSQL data types match the ORM. ``timestamp without
time zone`` does not match ``timestamptz``. Then create any missing non-unique
indexes only.
Mismatch raises ``DomesticOdsSchemaMismatchError`` so Alembic stops instead of
silently diverging.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base
from app.modules.pmc_domestic.models import PMC_DOMESTIC_ODS_TABLES

TABLE_ORDER: Final[tuple[str, ...]] = (
    "ods_lingxing_domestic_warehouses",
    "ods_lingxing_domestic_inventory",
    "ods_lingxing_domestic_batches",
    "ods_lingxing_domestic_inventory_events",
)

_DIALECT = postgresql.dialect()


class DomesticOdsSchemaMismatchError(RuntimeError):
    """Existing table shape does not match the registered ORM metadata."""


def _normalize_pg_type(
    data_type: str,
    udt_name: str,
    character_maximum_length: int | None,
) -> str:
    if udt_name == "uuid":
        return "uuid"
    if udt_name == "jsonb":
        return "jsonb"
    if udt_name == "int4":
        return "integer"
    if udt_name == "text":
        return "text"
    if udt_name == "varchar":
        if character_maximum_length is None:
            return "varchar"
        return f"varchar({character_maximum_length})"
    if data_type == "timestamp with time zone":
        return "timestamptz"
    return data_type


def _orm_column_types(table_name: str) -> dict[str, tuple[str, bool]]:
    table = Base.metadata.tables[table_name]
    out: dict[str, tuple[str, bool]] = {}
    for column in table.columns:
        compiled = column.type.compile(dialect=_DIALECT).lower()
        if "uuid" in compiled:
            token = "uuid"
        elif "jsonb" in compiled:
            token = "jsonb"
        elif compiled == "integer":
            token = "integer"
        elif compiled == "text":
            token = "text"
        elif "timestamp with time zone" in compiled:
            token = "timestamptz"
        elif compiled.startswith("varchar(") or compiled == "varchar":
            token = compiled
        else:
            token = compiled
        out[column.name] = (token, not column.nullable)
    return out


def _load_db_columns(connection: Connection, table_name: str) -> dict[str, tuple[str, bool]]:
    rows = connection.execute(
        text(
            """
            select column_name, data_type, udt_name, is_nullable, character_maximum_length
            from information_schema.columns
            where table_schema = 'public' and table_name = :table_name
            order by ordinal_position
            """
        ),
        {"table_name": table_name},
    ).all()
    return {
        row.column_name: (
            _normalize_pg_type(row.data_type, row.udt_name, row.character_maximum_length),
            row.is_nullable == "NO",
        )
        for row in rows
    }


def _verify_columns(table_name: str, db_columns: dict[str, tuple[str, bool]]) -> None:
    expected = _orm_column_types(table_name)
    if set(db_columns) != set(expected):
        missing = set(expected) - set(db_columns)
        extra = set(db_columns) - set(expected)
        raise DomesticOdsSchemaMismatchError(
            f"{table_name}: column set mismatch missing={sorted(missing)!r} extra={sorted(extra)!r}"
        )
    for name, (exp_type, exp_nullable) in expected.items():
        act_type, act_nullable = db_columns[name]
        if exp_type != act_type:
            raise DomesticOdsSchemaMismatchError(
                f"{table_name}.{name}: type expected {exp_type!r} found {act_type!r}"
            )
        if exp_nullable != act_nullable:
            raise DomesticOdsSchemaMismatchError(
                f"{table_name}.{name}: nullable expected {exp_nullable} found {act_nullable}"
            )


def _existing_index_names(connection: Connection, table_name: str) -> set[str]:
    rows = connection.execute(
        text(
            """
            select indexname
            from pg_indexes
            where schemaname = 'public' and tablename = :table_name
            """
        ),
        {"table_name": table_name},
    ).all()
    return {row.indexname for row in rows}


def _create_table(connection: Connection, table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    connection.execute(CreateTable(table))
    for index in table.indexes:
        if index.name:
            connection.execute(CreateIndex(index))


def _ensure_indexes(connection: Connection, table_name: str) -> None:
    existing = _existing_index_names(connection, table_name)
    table = Base.metadata.tables[table_name]
    for index in table.indexes:
        if index.name and index.name not in existing:
            connection.execute(CreateIndex(index))


def adopt_domestic_ods_tables(connection: Connection | Engine) -> None:
    """Create or adopt all four domestic ODS tables on a live PostgreSQL connection."""

    if isinstance(connection, Engine):
        with connection.connect() as conn:
            with conn.begin():
                _adopt_on_connection(conn)
        return
    _adopt_on_connection(connection)


def _adopt_on_connection(conn: Connection) -> None:
    inspector = inspect(conn)
    for table_name in TABLE_ORDER:
        if table_name not in PMC_DOMESTIC_ODS_TABLES:
            raise DomesticOdsSchemaMismatchError(f"unknown domestic ODS table {table_name}")
        if not inspector.has_table(table_name, schema="public"):
            _create_table(conn, table_name)
            continue
        db_columns = _load_db_columns(conn, table_name)
        _verify_columns(table_name, db_columns)
        _ensure_indexes(conn, table_name)
