"""Feishu snapshots are opt-in, audited and never assign IAM privileges."""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.iam.feishu_directory_service import FeishuDirectoryUser


def canonical_snapshot(
    departments: tuple[dict[str, str], ...],
    users: tuple[FeishuDirectoryUser, ...],
) -> tuple[str, list[dict[str, object]], list[dict[str, object]]]:
    """Normalize and hash only stable identities; reject duplicate or missing IDs."""
    dept_rows: list[dict[str, object]] = []
    seen_depts: set[str] = set()
    for item in departments:
        department_id = str(item.get("department_id") or "").strip()
        if not department_id or department_id in seen_depts:
            raise ValueError("Invalid or duplicate Feishu department identity")
        seen_depts.add(department_id)
        dept_rows.append({
            "department_id": department_id,
            "parent_department_id": str(item.get("parent_department_id") or "0"),
            "name": str(item.get("name") or department_id),
            "leader_user_id": str(item.get("leader_user_id") or ""),
        })
    users_by_id: dict[str, dict[str, object]] = {}
    for user in users:
        if not user.open_id or user.open_id in users_by_id:
            raise ValueError("Invalid or duplicate Feishu open_id")
        users_by_id[user.open_id] = {
            "open_id": user.open_id,
            "name": user.name,
            "department_ids": sorted(set(user.department_ids)),
            "is_active": user.is_active,
            "is_frozen": user.is_frozen,
            "is_resigned": user.is_resigned,
        }
    dept_rows.sort(key=lambda row: str(row["department_id"]))
    user_rows = [users_by_id[key] for key in sorted(users_by_id)]
    payload = {"departments": dept_rows, "users": user_rows}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return digest, dept_rows, user_rows


def apply_snapshot(
    session: Session,
    *,
    expected_hash: str,
    departments: tuple[dict[str, str], ...],
    users: tuple[FeishuDirectoryUser, ...],
    requested_by: str,
) -> str:
    """Explicit transaction only; never deletes absent users or grants permissions."""
    digest, dept_rows, user_rows = canonical_snapshot(departments, users)
    if not dept_rows or not user_rows or digest != expected_hash:
        raise ValueError("Feishu snapshot empty or changed since preview")
    run_id = uuid4()
    session.execute(
        text("""
        INSERT INTO iam_feishu_org_sync_runs
            (id, snapshot_hash, department_count, employee_count, requested_by)
        VALUES (:id, :hash, :departments, :employees, :requested_by)
        """),
        {"id": run_id, "hash": digest, "departments": len(dept_rows),
         "employees": len(user_rows), "requested_by": requested_by},
    )
    for dept in dept_rows:
        session.execute(
            text("""
            INSERT INTO iam_feishu_departments
                (department_id, parent_department_id, name, leader_user_id, last_seen_run_id)
            VALUES (:department_id, :parent_department_id, :name, :leader_user_id, :run_id)
            ON CONFLICT (department_id) DO UPDATE SET
                parent_department_id = excluded.parent_department_id,
                name = excluded.name,
                leader_user_id = excluded.leader_user_id,
                last_seen_run_id = excluded.last_seen_run_id,
                updated_at = now()
            """),
            {**dept, "run_id": run_id},
        )
    for user in user_rows:
        session.execute(
            text("""
            INSERT INTO iam_feishu_employees
                (open_id, name, department_ids, is_active, is_frozen,
                 is_resigned, last_seen_run_id)
            VALUES (:open_id, :name, CAST(:department_ids AS jsonb), :is_active,
                    :is_frozen, :is_resigned, :run_id)
            ON CONFLICT (open_id) DO UPDATE SET
                name = excluded.name,
                department_ids = excluded.department_ids,
                is_active = excluded.is_active,
                is_frozen = excluded.is_frozen,
                is_resigned = excluded.is_resigned,
                last_seen_run_id = excluded.last_seen_run_id,
                updated_at = now()
            """),
            {**user, "department_ids": json.dumps(user["department_ids"]),
             "run_id": run_id},
        )
    return str(run_id)
