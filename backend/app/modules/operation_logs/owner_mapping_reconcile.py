"""Safe reconciliation for account-scoped Lingxing owner mappings."""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.integration_sync.repository import IntegrationSyncRepository


def normalize_owner_name(value: object) -> str:
    """Normalize a name for exact matching; never use fuzzy matching."""
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def matching_user_ids(
    owner_names: Sequence[str],
    users: Sequence[Mapping[str, Any]],
) -> set[int]:
    """Return distinct eligible users matching an owner name exactly."""
    names = {normalize_owner_name(value) for value in owner_names}
    names.discard("")
    matched: set[int] = set()

    for user in users:
        aliases = {
            normalize_owner_name(user.get("display_name")),
            normalize_owner_name(user.get("feishu_name")),
        }
        aliases.discard("")
        if names.intersection(aliases):
            matched.add(int(user["id"]))

    return matched


def _is_admin_actor(session: Session, user_id: int) -> bool:
    row = (
        session.execute(
            text("""
            select is_active, is_super_admin
            from app_users
            where id = :user_id
        """),
            {"user_id": user_id},
        )
        .mappings()
        .one_or_none()
    )

    if row is None or not bool(row["is_active"]):
        return False
    if bool(row["is_super_admin"]):
        return True

    return bool(
        session.scalar(
            text("""
        select exists (
            select 1
            from app_user_roles ur
            join app_roles r on r.id = ur.role_id
            where ur.user_id = :user_id
              and r.role_key = 'admin'
        )
    """),
            {"user_id": user_id},
        )
    )


def _onboarding_admin_actor(session: Session, target_user_id: int) -> int | None:
    actors = (
        session.execute(
            text("""
            select actor_user_id
            from iam_audit_events
            where target_type = 'user'
              and target_key = :target_key
              and event_type in ('user.created', 'user.updated')
              and actor_user_id is not null
            order by created_at desc, id desc
        """),
            {"target_key": str(target_user_id)},
        )
        .scalars()
        .all()
    )

    for actor in actors:
        actor_id = int(actor)
        if _is_admin_actor(session, actor_id):
            return actor_id
    return None


def reconcile_owner_mappings(
    session: Session,
    *,
    accounts: Sequence[str] | None = None,
    actor_user_id: int | None = None,
    apply: bool = False,
    target_user_id: int | None = None,
    use_onboarding_actor: bool = False,
) -> dict[str, Any]:
    """Preview or safely create mappings. Never overwrite an existing mapping.

    Automatic assignments require a unique exact name match, an eligible
    active user, an unambiguous source owner identity and an admin audit actor.
    """
    if apply:
        raise RuntimeError(
            "Automatic owner UID binding is forbidden; use administrator explicit assignment"
        )

    if accounts is None:
        accounts = tuple(IntegrationSyncRepository(session).list_configured_source_account_refs())
    else:
        accounts = tuple(dict.fromkeys(str(a) for a in accounts if str(a)))

    if not accounts:
        return {
            "identities_scanned": 0,
            "considered": 0,
            "already_mapped": 0,
            "ready_to_map": 0,
            "created": 0,
            "ambiguous_owner_identity": 0,
            "ambiguous_user_match": 0,
            "no_matching_user": 0,
            "mapping_conflict": 0,
            "no_admin_actor": 0,
            "details": [],
        }

    owner_rows = (
        session.execute(
            text("""
        select
            source_account_ref,
            btrim(owner_uid) as owner_uid,
            count(distinct nullif(btrim(owner_name), '')) as name_count,
            min(nullif(btrim(owner_name), '')) as owner_name,
            array_agg(
                distinct nullif(btrim(owner_name), '')
            ) filter (
                where nullif(btrim(owner_name), '') is not null
            ) as owner_names,
            count(*) as product_rows
        from dwd_lingxing_sku_product_info_current
        where source_account_ref = any(:accounts)
          and nullif(btrim(owner_uid), '') is not null
        group by source_account_ref, btrim(owner_uid)
        order by source_account_ref, btrim(owner_uid)
    """),
            {"accounts": list(accounts)},
        )
        .mappings()
        .all()
    )

    all_users = (
        session.execute(
            text("""
        select id, display_name, feishu_name, is_active, is_super_admin
        from app_users
    """)
        )
        .mappings()
        .all()
    )

    role_user_ids = {
        int(value)
        for value in session.execute(
            text("""
            select distinct ur.user_id
            from app_user_roles ur
            join app_roles r on r.id = ur.role_id
            left join app_role_permissions rp on rp.role_id = r.id
            where r.role_key = 'admin'
               or rp.permission_key in (
                   'page:operations:log:view',
                   'page:sales:daily-sales:view'
               )
        """)
        )
        .scalars()
        .all()
    }

    users = [
        row
        for row in all_users
        if bool(row["is_active"])
        and (bool(row["is_super_admin"]) or int(row["id"]) in role_user_ids)
    ]

    mapping_rows = (
        session.execute(
            text("""
        select source_account_ref, owner_uid, app_user_id
        from ops_lingxing_owner_user_mappings
        where source_account_ref = any(:accounts)
    """),
            {"accounts": list(accounts)},
        )
        .mappings()
        .all()
    )

    existing = {
        (str(row["source_account_ref"]), str(row["owner_uid"]).strip()): int(row["app_user_id"])
        for row in mapping_rows
    }

    details: list[dict[str, Any]] = []

    for owner in owner_rows:
        account = str(owner["source_account_ref"])
        owner_uid = str(owner["owner_uid"]).strip()
        owner_name = str(owner["owner_name"] or "").strip()
        owner_names = [
            str(name).strip() for name in (owner["owner_names"] or []) if str(name or "").strip()
        ]

        candidates = matching_user_ids(owner_names, users)

        # User onboarding only reconciles identities that could belong to
        # that user. Other owners are left untouched.
        if target_user_id is not None and target_user_id not in candidates:
            continue

        key = (account, owner_uid)
        mapped_user_id = existing.get(key)

        item: dict[str, Any] = {
            "source_account_ref": account,
            "owner_uid": owner_uid,
            "owner_name": owner_name,
            "product_rows": int(owner["product_rows"]),
            "candidate_user_count": len(candidates),
            "mapped_user_id": mapped_user_id,
        }

        if int(owner["name_count"] or 0) != 1 or not owner_name:
            item["status"] = "ambiguous_owner_identity"
            details.append(item)
            continue

        if not candidates:
            item["status"] = (
                "mapped_name_unmatched" if mapped_user_id is not None else "no_matching_user"
            )
            details.append(item)
            continue

        if len(candidates) != 1:
            item["status"] = "ambiguous_user_match"
            details.append(item)
            continue

        matched_user_id = next(iter(candidates))
        item["candidate_user_id"] = matched_user_id

        if mapped_user_id is not None:
            item["status"] = (
                "already_mapped" if mapped_user_id == matched_user_id else "mapping_conflict"
            )
            details.append(item)
            continue

        if not apply:
            item["status"] = "ready_to_map"
            details.append(item)
            continue

        effective_actor: int | None = None

        if actor_user_id is not None:
            if _is_admin_actor(session, actor_user_id):
                effective_actor = actor_user_id
        elif use_onboarding_actor:
            effective_actor = _onboarding_admin_actor(session, matched_user_id)

        if effective_actor is None:
            item["status"] = "no_admin_actor"
            details.append(item)
            continue

        params = {
            "account": account,
            "owner_uid": owner_uid,
            "user_id": matched_user_id,
            "actor": effective_actor,
        }

        inserted = session.execute(
            text("""
            insert into ops_lingxing_owner_user_mappings
                (source_account_ref, owner_uid, app_user_id, updated_by_user_id)
            values (:account, :owner_uid, :user_id, :actor)
            on conflict (source_account_ref, owner_uid) do nothing
            returning id
        """),
            params,
        ).scalar_one_or_none()

        if inserted is None:
            current_user_id = session.scalar(
                text("""
                select app_user_id
                from ops_lingxing_owner_user_mappings
                where source_account_ref = :account
                  and owner_uid = :owner_uid
            """),
                params,
            )

            item["mapped_user_id"] = current_user_id
            item["status"] = (
                "already_mapped" if current_user_id == matched_user_id else "mapping_conflict"
            )
            details.append(item)
            continue

        session.execute(
            text("""
            insert into ops_lingxing_owner_mapping_audit
                (source_account_ref, owner_uid, before_user_id,
                 after_user_id, actor_user_id, action)
            values
                (:account, :owner_uid, null, :user_id, :actor, 'assign')
        """),
            params,
        )

        existing[key] = matched_user_id
        item["mapped_user_id"] = matched_user_id
        item["status"] = "mapped"
        details.append(item)

    counts = Counter(item["status"] for item in details)

    return {
        "identities_scanned": len(owner_rows),
        "considered": len(details),
        "already_mapped": counts["already_mapped"],
        "ready_to_map": counts["ready_to_map"],
        "created": counts["mapped"],
        "ambiguous_owner_identity": counts["ambiguous_owner_identity"],
        "ambiguous_user_match": counts["ambiguous_user_match"],
        "no_matching_user": counts["no_matching_user"],
        "mapped_name_unmatched": counts["mapped_name_unmatched"],
        "mapping_conflict": counts["mapping_conflict"],
        "no_admin_actor": counts["no_admin_actor"],
        "details": details,
    }
