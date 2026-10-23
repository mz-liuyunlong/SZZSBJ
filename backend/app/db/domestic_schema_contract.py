"""Strict PostgreSQL adoption checks shared by the domestic migrations.

CHECK expressions are parsed by PostgreSQL on an empty temporary table. This
avoids accepting a different expression by stripping parentheses or casts in
Python. Only session-local contract objects are created; business tables and
their rows are never repaired or replaced by this validator.
"""

from collections import Counter
from collections.abc import Sequence
from typing import Any, NoReturn
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.schema import CreateTable, DropTable


def _constraints(bind: sa.Connection, qualified: str) -> Sequence[sa.Row[Any]]:
    rows = bind.execute(
        sa.text("""
            SELECT c.contype, c.convalidated, c.condeferrable, c.condeferred,
                   c.connoinherit, c.confdeltype, c.confupdtype, c.confmatchtype,
                   rn.nspname AS ref_schema, r.relname AS ref_table,
                   pg_get_expr(c.conbin, c.conrelid) AS expression,
                   ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY k(n,ord)
                         JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.n
                         ORDER BY k.ord) AS columns,
                   ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY k(n,ord)
                         JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.n
                         ORDER BY k.ord) AS ref_columns
            FROM pg_constraint c
            LEFT JOIN pg_class r ON r.oid=c.confrelid
            LEFT JOIN pg_namespace rn ON rn.oid=r.relnamespace
            WHERE c.conrelid=CAST(:qualified AS regclass)
        """),
        {"qualified": qualified},
    ).all()
    return list(rows)


def require_domestic_table(
    bind: sa.Connection,
    table: sa.Table,
    *,
    error_type: type[RuntimeError] = RuntimeError,
    prefix: str = "DOMESTIC_SCHEMA",
) -> None:
    """Require the complete declared contract, with validated, usable constraints.

    The caller supplies frozen migration DDL (or the original ODS metadata).
    Extra constraints/indexes are rejected rather than silently adopted.
    """
    qualified = f"public.{table.name}"

    def fail(part: str) -> NoReturn:
        raise error_type(f"{prefix}:{table.name}:{part}_MISMATCH")

    kind = bind.scalar(
        sa.text("SELECT relkind FROM pg_class WHERE oid=to_regclass(:q)"), {"q": qualified}
    )
    if kind != "r":
        fail("TABLE")
    # Hold the adopted relation stable until the migration transaction completes.
    quoted = bind.dialect.identifier_preparer.quote(table.name)
    bind.execute(sa.text(f"LOCK TABLE public.{quoted} IN SHARE MODE"))
    actual_columns = {
        row.name: (row.type_name, row.required, row.default_expr, row.identity, row.generated)
        for row in bind.execute(
            sa.text("""
            SELECT a.attname AS name, format_type(a.atttypid,a.atttypmod) AS type_name,
                   a.attnotnull AS required, pg_get_expr(d.adbin,d.adrelid) AS default_expr,
                   a.attidentity AS identity, a.attgenerated AS generated
            FROM pg_attribute a LEFT JOIN pg_attrdef d
              ON d.adrelid=a.attrelid AND d.adnum=a.attnum
            WHERE a.attrelid=CAST(:q AS regclass) AND a.attnum>0 AND NOT a.attisdropped
        """),
            {"q": qualified},
        )
    }
    expected_columns = {
        c.name: (
            c.type.compile(dialect=bind.dialect)
            .lower()
            .replace("varchar", "character varying")
            .replace(", ", ","),
            not c.nullable,
            str(c.server_default.arg) if c.server_default is not None else None,
            "",
            "",
        )
        for c in table.columns
    }
    if actual_columns != expected_columns:
        fail("COLUMNS")
    rows = _constraints(bind, qualified)
    if any(
        not r.convalidated
        or r.condeferrable
        or r.condeferred
        or (r.contype == "c" and r.connoinherit)
        for r in rows
    ):
        fail("CONSTRAINT_VALIDATION")
    expected_pk = [tuple(c.name for c in table.primary_key.columns)]
    if [tuple(r.columns) for r in rows if r.contype == "p"] != expected_pk:
        fail("PRIMARY_KEY")
    expected_unique = Counter(
        tuple(c.name for c in item.columns)
        for item in table.constraints
        if isinstance(item, sa.UniqueConstraint)
    )
    if Counter(tuple(r.columns) for r in rows if r.contype == "u") != expected_unique:
        fail("UNIQUE")
    expected_fks: Counter[tuple[Any, ...]] = Counter()
    actions = {
        None: "a",
        "NO ACTION": "a",
        "RESTRICT": "r",
        "CASCADE": "c",
        "SET NULL": "n",
        "SET DEFAULT": "d",
    }
    for constraint in table.foreign_key_constraints:
        targets = [item.target_fullname.split(".") for item in constraint.elements]
        expected_fks[
            (
                tuple(constraint.column_keys),
                targets[0][-3] if len(targets[0]) == 3 else "public",
                targets[0][-2],
                tuple(t[-1] for t in targets),
                actions[constraint.ondelete],
                actions[constraint.onupdate],
                "f" if constraint.match == "FULL" else "s",
            )
        ] += 1
    actual_fks = Counter(
        (
            tuple(r.columns),
            r.ref_schema,
            r.ref_table,
            tuple(r.ref_columns),
            r.confdeltype,
            r.confupdtype,
            r.confmatchtype,
        )
        for r in rows
        if r.contype == "f"
    )
    if actual_fks != expected_fks:
        fail("FOREIGN_KEY")
    if any(r.contype not in {"p", "u", "c", "f"} for r in rows):
        fail("CONSTRAINT")
    # Have the same PostgreSQL server canonicalize the exact frozen CHECK DDL.
    temporary = sa.Table(
        "domestic_contract_" + uuid4().hex,
        sa.MetaData(),
        *(sa.Column(c.name, c.type, nullable=c.nullable) for c in table.columns),
        *(
            sa.CheckConstraint(str(c.sqltext))
            for c in table.constraints
            if isinstance(c, sa.CheckConstraint)
        ),
        prefixes=["TEMPORARY"],
        postgresql_on_commit="DROP",
    )
    bind.execute(CreateTable(temporary))
    try:
        expected_checks = Counter(
            r.expression for r in _constraints(bind, temporary.name) if r.contype == "c"
        )
        if Counter(r.expression for r in rows if r.contype == "c") != expected_checks:
            fail("CHECK")
    finally:
        bind.execute(DropTable(temporary))
    indexes = bind.execute(
        sa.text("""
        SELECT idx.relname AS name, i.indisvalid, i.indisready, i.indislive,
               i.indisunique, i.indisprimary, am.amname,
               pg_get_expr(i.indpred,i.indrelid) AS predicate,
               i.indnatts, i.indnkeyatts,
               ARRAY(SELECT pg_get_indexdef(i.indexrelid,k,true)
                     FROM generate_series(1,i.indnkeyatts) k) AS columns,
               EXISTS(SELECT 1 FROM pg_constraint c WHERE c.conindid=i.indexrelid
                      AND c.contype IN ('p','u')) AS constraint_index
        FROM pg_index i JOIN pg_class idx ON idx.oid=i.indexrelid
        JOIN pg_am am ON am.oid=idx.relam
        WHERE i.indrelid=CAST(:q AS regclass)
    """),
        {"q": qualified},
    ).all()
    if any(not i.indisvalid or not i.indisready or not i.indislive for i in indexes):
        fail("INDEX_VALIDITY")
    # The domestic contracts declare ordinary ordered btree indexes only.
    actual_indexes = {
        i.name: (
            tuple(i.columns),
            i.indisunique,
            i.amname,
            i.predicate,
            i.indnatts == i.indnkeyatts,
        )
        for i in indexes
        if not i.constraint_index
    }
    expected_indexes = {
        i.name: (tuple(c.name for c in i.columns), bool(i.unique), "btree", None, True)
        for i in table.indexes
    }
    if actual_indexes != expected_indexes:
        fail("INDEX")
