"""Adopt the four domestic warehouse ODS tables.

Fresh environments, where none of the four tables exist, create them from ORM
metadata. If any one of the four is already present, the other three must be
present too. A missing table is an error: this migration does not create a
replacement empty table, because that would hide lost data.

When all four exist, columns (including varchar length), nullability, primary
keys, unique constraints, foreign keys, check expressions and indexes must
match the ORM. Nothing is altered and no rows are written.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, text
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

_TYPE_ALIASES: Final[Mapping[str, str]] = {
    "character varying": "varchar",
    "timestamp with time zone": "timestamptz",
}

ColumnShape = tuple[str, int | None, bool]
IndexShape = tuple[str, bool, tuple[str, ...]]


class DomesticOdsSchemaMismatchError(RuntimeError):
    """Existing table shape does not match the registered ORM metadata."""


def _normalize_pg_type(data_type: str, udt_name: str) -> str:
    base = _TYPE_ALIASES.get(data_type, data_type)
    if udt_name == "uuid":
        return "uuid"
    if udt_name == "jsonb":
        return "jsonb"
    if udt_name == "int4":
        return "integer"
    if udt_name == "text":
        return "text"
    if udt_name == "varchar":
        return "varchar"
    if "timestamp" in base:
        return "timestamptz"
    return base


def _column_token(compiled: str) -> tuple[str, int | None]:
    if "uuid" in compiled:
        return "uuid", None
    if "jsonb" in compiled:
        return "jsonb", None
    if "integer" in compiled:
        return "integer", None
    if "timestamp" in compiled:
        return "timestamptz", None
    if compiled == "text" or compiled.startswith("text"):
        return "text", None
    match = re.search(r"\((\d+)\)", compiled)
    length = int(match.group(1)) if match else None
    return "varchar", length


def _orm_column_types(table_name: str) -> dict[str, ColumnShape]:
    table = Base.metadata.tables[table_name]
    shapes: dict[str, ColumnShape] = {}
    for column in table.columns:
        compiled = column.type.compile(dialect=_DIALECT).lower()
        token, length = _column_token(compiled)
        shapes[column.name] = (token, length, not column.nullable)
    return shapes


def _load_db_columns(connection: Connection, table_name: str) -> dict[str, ColumnShape]:
    rows = connection.execute(
        text(
            """
            select column_name, data_type, udt_name, character_maximum_length, is_nullable
            from information_schema.columns
            where table_schema = 'public' and table_name = :table_name
            order by ordinal_position
            """
        ),
        {"table_name": table_name},
    ).all()
    loaded: dict[str, ColumnShape] = {}
    for row in rows:
        token = _normalize_pg_type(row.data_type, row.udt_name)
        length = row.character_maximum_length if token == "varchar" else None
        loaded[row.column_name] = (token, length, row.is_nullable == "NO")
    return loaded


def _verify_columns(table_name: str, db_columns: dict[str, ColumnShape]) -> None:
    expected = _orm_column_types(table_name)
    if set(db_columns) != set(expected):
        missing = sorted(set(expected) - set(db_columns))
        extra = sorted(set(db_columns) - set(expected))
        raise DomesticOdsSchemaMismatchError(
            f"{table_name}: column set mismatch missing={missing!r} extra={extra!r}"
        )
    for name, (exp_type, exp_length, exp_required) in expected.items():
        act_type, act_length, act_required = db_columns[name]
        if (exp_type, exp_length) != (act_type, act_length):
            raise DomesticOdsSchemaMismatchError(
                f"{table_name}.{name}: type expected {exp_type}({exp_length}) "
                f"found {act_type}({act_length})"
            )
        if exp_required != act_required:
            raise DomesticOdsSchemaMismatchError(
                f"{table_name}.{name}: required expected {exp_required} found {act_required}"
            )


def _constraint_columns(
    connection: Connection, table_name: str, constraint_type: str
) -> set[tuple[str, ...]]:
    rows = connection.execute(
        text(
            """
            select tc.constraint_name, kcu.column_name
            from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu
              on tc.constraint_name = kcu.constraint_name
             and tc.table_schema = kcu.table_schema
             and tc.table_name = kcu.table_name
            where tc.table_schema = 'public'
              and tc.table_name = :table_name
              and tc.constraint_type = :constraint_type
            order by tc.constraint_name, kcu.ordinal_position
            """
        ),
        {"table_name": table_name, "constraint_type": constraint_type},
    ).all()
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row.constraint_name, []).append(row.column_name)
    return {tuple(columns) for columns in grouped.values()}


def _load_foreign_keys(
    connection: Connection, table_name: str
) -> set[tuple[tuple[str, ...], str, str]]:
    rows = connection.execute(
        text(
            """
            select tc.constraint_name, kcu.column_name, ccu.table_name as ref_table, rc.delete_rule
            from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu
              on tc.constraint_name = kcu.constraint_name
             and tc.table_schema = kcu.table_schema
             and tc.table_name = kcu.table_name
            join information_schema.referential_constraints rc
              on tc.constraint_name = rc.constraint_name
             and tc.table_schema = rc.constraint_schema
            join information_schema.constraint_column_usage ccu
              on rc.unique_constraint_name = ccu.constraint_name
             and rc.unique_constraint_schema = ccu.constraint_schema
            where tc.table_schema = 'public'
              and tc.table_name = :table_name
              and tc.constraint_type = 'FOREIGN KEY'
            order by tc.constraint_name, kcu.ordinal_position
            """
        ),
        {"table_name": table_name},
    ).all()
    grouped: dict[str, tuple[list[str], str, str]] = {}
    for row in rows:
        current = grouped.get(row.constraint_name)
        columns = [] if current is None else current[0]
        columns.append(row.column_name)
        grouped[row.constraint_name] = (columns, row.ref_table, row.delete_rule)
    return {
        (tuple(columns), ref_table, (delete_rule or "NO ACTION").upper())
        for columns, ref_table, delete_rule in grouped.values()
    }


def _normalize_check(expression: str) -> str:
    normalized = expression.lower().removeprefix("check")
    normalized = normalized.replace("trim(both from ", "trim(")
    normalized = re.sub(r"\s+", "", normalized)
    while normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1]
    return normalized


def _load_checks(connection: Connection, table_name: str) -> set[str]:
    rows = connection.execute(
        text(
            """
            select pg_get_constraintdef(con.oid) as definition
            from pg_constraint con
            join pg_class rel on rel.oid = con.conrelid
            join pg_namespace nsp on nsp.oid = rel.relnamespace
            where con.contype = 'c'
              and nsp.nspname = 'public'
              and rel.relname = :table_name
            """
        ),
        {"table_name": table_name},
    ).all()
    return {_normalize_check(row.definition) for row in rows}


def _verify_keys(connection: Connection, table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    expected_pk = {tuple(column.name for column in table.primary_key.columns)}
    actual_pk = _constraint_columns(connection, table_name, "PRIMARY KEY")
    if actual_pk != expected_pk:
        raise DomesticOdsSchemaMismatchError(
            f"{table_name}: primary key expected {sorted(expected_pk)!r} "
            f"found {sorted(actual_pk)!r}"
        )
    expected_unique = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    actual_unique = _constraint_columns(connection, table_name, "UNIQUE")
    if actual_unique != expected_unique:
        raise DomesticOdsSchemaMismatchError(
            f"{table_name}: unique constraints expected {sorted(expected_unique)!r} "
            f"found {sorted(actual_unique)!r}"
        )
    expected_fk = {
        (
            tuple(column.name for column in constraint.columns),
            constraint.elements[0].column.table.name,
            (constraint.ondelete or "NO ACTION").upper(),
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    actual_fk = _load_foreign_keys(connection, table_name)
    if actual_fk != expected_fk:
        raise DomesticOdsSchemaMismatchError(
            f"{table_name}: foreign keys expected {sorted(expected_fk)!r} "
            f"found {sorted(actual_fk)!r}"
        )
    expected_checks = {
        _normalize_check(str(constraint.sqltext))
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    actual_checks = _load_checks(connection, table_name)
    if actual_checks != expected_checks:
        raise DomesticOdsSchemaMismatchError(
            f"{table_name}: check constraints expected {sorted(expected_checks)!r} "
            f"found {sorted(actual_checks)!r}"
        )


def _load_indexes(connection: Connection, table_name: str) -> list[IndexShape]:
    rows = connection.execute(
        text(
            """
            select index_class.relname as index_name,
                   idx.indisunique as is_unique,
                   attr.attname as column_name,
                   key_ord.ordinality as column_ordinal
            from pg_index idx
            join pg_class table_class on table_class.oid = idx.indrelid
            join pg_class index_class on index_class.oid = idx.indexrelid
            join pg_namespace nsp on nsp.oid = table_class.relnamespace
            join lateral unnest(idx.indkey) with ordinality as key_ord(attnum, ordinality)
              on true
            join pg_attribute attr
              on attr.attrelid = table_class.oid
             and attr.attnum = key_ord.attnum
            where nsp.nspname = 'public'
              and table_class.relname = :table_name
            order by index_class.relname, key_ord.ordinality
            """
        ),
        {"table_name": table_name},
    ).all()
    grouped: dict[str, tuple[bool, list[str]]] = {}
    for row in rows:
        unique, columns = grouped.get(row.index_name, (row.is_unique, []))
        columns.append(row.column_name)
        grouped[row.index_name] = (unique, columns)
    return [(name, unique, tuple(columns)) for name, (unique, columns) in grouped.items()]


def _verify_indexes(connection: Connection, table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    actual = _load_indexes(connection, table_name)
    expected_unique = {tuple(column.name for column in table.primary_key.columns)}
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            expected_unique.add(tuple(column.name for column in constraint.columns))
    actual_unique = {columns for _name, unique, columns in actual if unique}
    if actual_unique != expected_unique:
        raise DomesticOdsSchemaMismatchError(
            f"{table_name}: unique indexes expected {sorted(expected_unique)!r} "
            f"found {sorted(actual_unique)!r}"
        )
    expected_named = {
        (index.name, bool(index.unique), tuple(column.name for column in index.columns))
        for index in table.indexes
        if index.name
    }
    actual_named = {(name, unique, columns) for name, unique, columns in actual if not unique}
    if actual_named != expected_named:
        raise DomesticOdsSchemaMismatchError(
            f"{table_name}: indexes expected {sorted(expected_named)!r} "
            f"found {sorted(actual_named)!r}"
        )


def _table_exists(connection: Connection, table_name: str) -> bool:
    found = connection.execute(
        text("select to_regclass(:qualified)"),
        {"qualified": f"public.{table_name}"},
    ).scalar_one()
    return found is not None


def _create_table(connection: Connection, table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    connection.execute(CreateTable(table))
    for index in table.indexes:
        if index.name:
            connection.execute(CreateIndex(index))


def _verify_existing(connection: Connection, table_name: str) -> None:
    _verify_columns(table_name, _load_db_columns(connection, table_name))
    _verify_keys(connection, table_name)
    _verify_indexes(connection, table_name)


def adopt_domestic_ods_tables(connection: Connection | Engine) -> None:
    """Create all four tables, or verify all four. Never replace a missing one."""

    if isinstance(connection, Engine):
        with connection.connect() as conn:
            with conn.begin():
                _adopt_on_connection(conn)
        return
    _adopt_on_connection(connection)


def _adopt_on_connection(conn: Connection) -> None:
    unknown = [name for name in TABLE_ORDER if name not in PMC_DOMESTIC_ODS_TABLES]
    if unknown:
        raise DomesticOdsSchemaMismatchError(f"unknown domestic ODS tables {unknown!r}")
    present = [name for name in TABLE_ORDER if _table_exists(conn, name)]
    if not present:
        for table_name in TABLE_ORDER:
            _create_table(conn, table_name)
        return
    missing = [name for name in TABLE_ORDER if name not in present]
    if missing:
        raise DomesticOdsSchemaMismatchError(
            f"domestic ODS tables are partially present; refusing to create missing={missing!r}"
        )
    for table_name in TABLE_ORDER:
        _verify_existing(conn, table_name)
