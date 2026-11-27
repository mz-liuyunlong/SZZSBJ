"""Resolve applicant display names only for already-authorized records."""

from sqlalchemy import bindparam, text


def _user_id(value):
    value = str(value or "")
    if not value.isascii() or not value.isdecimal() or len(value) > 19:
        return None
    number = int(value)
    if number <= 0 or number > 9223372036854775807:
        return None
    if str(number) != value:
        return None
    return number


def resolve_names(session, applicant_ids):
    ids = sorted({value for raw in applicant_ids if (value := _user_id(raw)) is not None})
    if not ids:
        return {}

    statement = text("""
        SELECT id, display_name, username
        FROM app_users
        WHERE id IN :ids
    """).bindparams(bindparam("ids", expanding=True))

    rows = session.execute(statement, {"ids": ids}).mappings().all()

    return {
        str(row["id"]): (
            str(row["display_name"] or "").strip() or str(row["username"] or "").strip() or None
        )
        for row in rows
    }


def attach_approval_names(session, data):
    """Keep the immutable applicant ID for authorization and auditing."""
    items = data.items if isinstance(getattr(data, "items", None), list) else [data]

    names = resolve_names(session, [item.applicant_id for item in items])
    for item in items:
        item.applicant_name = names.get(str(item.applicant_id))
    return data


def attach_clearance_names(session, data):
    """Resolve clearance actors using the authoritative IAM read session."""
    items = data.get("items")
    if items is None:
        item = data.get("application")
        items = [item] if isinstance(item, dict) else []

    names = resolve_names(session, [item.get("applicant_ref") for item in items])
    for item in items:
        item["applicant_name"] = names.get(str(item.get("applicant_ref")))
    return data
