"""Manual SKU state: authoritative business table, versioned audit, no source mutation."""

from __future__ import annotations

import json
import os
from uuid import UUID, uuid4

from sqlalchemy import text

from .sku_progress_purchase import ELIGIBILITY, fail


def save_progress(
    db,
    accounts,
    actor,
    *,
    account: str,
    sku_id: UUID,
    version: int,
    status: str,
    reason: str | None,
    remark: str,
):
    if account not in accounts:
        fail("SKU_PROGRESS_SCOPE_DENIED", "无该账号的数据权限", 403)
    if os.getenv("NEW_PRODUCTS_READ_DATABASE_URL", "").strip():
        fail("SKU_PROGRESS_SPLIT_SOURCE_DENIED", "当前为独立只读数据环境，禁止保存", 403)
    remark = remark.strip()
    reason = (reason or "").strip() or None
    if (
        status not in ("in_progress", "paused", "terminated", "completed")
        or not remark
        or len(remark) > 500
    ):
        fail("SKU_PROGRESS_MANUAL_INVALID", "请选择推进状态并填写备注（最多500字）", 422)
    if status in ("paused", "terminated") and (not reason or len(reason) > 128):
        fail("SKU_PROGRESS_REASON_REQUIRED", "暂停或终止推进必须填写原因", 422)
    if status not in ("paused", "terminated"):
        reason = None
    p = {"account": account, "sku_id": sku_id}
    db.execute(text("SET LOCAL lock_timeout='3s'"))
    if db.execute(ELIGIBILITY, p).mappings().one_or_none() is None:
        fail("SKU_PROGRESS_NOT_ELIGIBLE", "SKU已不在小批量测品范围", 409)
    result = db.execute(
        text(
            "INSERT INTO biz_new_product_sku_progress\n"
            "       (id,source_account_ref,sku_identity_id,entered_at)\n"
            "       VALUES(:id,:account,:sku_id,now()) ON "
            "CONFLICT(source_account_ref,sku_identity_id) DO NOTHING"
        ),
        {**p, "id": uuid4()},
    )
    created = result.rowcount == 1
    old = (
        db.execute(
            text(
                "SELECT id,version,progress_status,reason_type,remark,manual_locked,exi"
                "ted_at\n"
                "       FROM biz_new_product_sku_progress WHERE "
                "source_account_ref=:account AND sku_identity_id=:sku_id FOR UPDATE"
            ),
            p,
        )
        .mappings()
        .one()
    )
    if version != (0 if created else old["version"]):
        fail("SKU_PROGRESS_VERSION_CONFLICT", "记录已变化，请刷新后重新编辑", 409)
    if old["exited_at"] is not None:
        fail("SKU_PROGRESS_EXITED", "SKU已退出推进范围", 409)
    # Reopening terminal states is not approved; notes on those states remain editable.
    if old["progress_status"] in ("completed", "terminated") and status != old["progress_status"]:
        fail("SKU_PROGRESS_TERMINAL", "已完成或终止的SKU暂不允许更改状态", 409)
    # Do not pause/terminate while an external purchase has an ambiguous outcome.
    if (
        status != "in_progress"
        and status != old["progress_status"]
        and db.scalar(
            text("""SELECT EXISTS(SELECT 1 FROM biz_new_product_sku_purchase_plans
        WHERE sku_progress_id=:id AND submission_status IN ('submitting','unknown'))"""),
            {"id": old["id"]},
        )
    ):
        fail("SKU_PROGRESS_PURCHASE_PENDING", "采购结果未确认，请先核对采购记录", 409)
    values = {
        "id": old["id"],
        "status": status,
        "reason": reason,
        "remark": remark,
        "actor": str(actor),
    }
    updated = db.execute(
        text(
            "UPDATE biz_new_product_sku_progress SET\n"
            "       progress_status=:status,manual_progress_status=:status,status_sourc"
            "e='manual',manual_locked=true,\n"
            "       reason_type=:reason,remark=:remark,manual_updated_by=:actor,manual_"
            "updated_at=now(),\n"
            "       updated_by=:actor,updated_at=now(),last_progress_at=now(),version=v"
            "ersion+1,\n"
            "       paused_at=CASE WHEN :status='paused' AND progress_status<>'paused' "
            "THEN now() ELSE paused_at END,\n"
            "       resumed_at=CASE WHEN :status='in_progress' AND "
            "progress_status='paused' THEN now() ELSE resumed_at END,\n"
            "       terminated_at=CASE WHEN :status='terminated' AND "
            "progress_status<>'terminated' THEN now() ELSE terminated_at END,\n"
            "       completed_at=CASE WHEN :status='completed' AND "
            "progress_status<>'completed' THEN now() ELSE completed_at END\n"
            "       WHERE id=:id RETURNING version"
        ),
        values,
    ).scalar_one()
    before = {
        k: old[k] for k in ("progress_status", "reason_type", "remark", "manual_locked", "version")
    }
    after = dict(
        progress_status=status,
        reason_type=reason,
        remark=remark,
        manual_locked=True,
        version=updated,
    )
    db.execute(
        text(
            "INSERT INTO biz_new_product_sku_progress_events\n"
            "       (id,sku_progress_id,event_type,actor_type,actor_ref,event_key,befor"
            "e_json,after_json,reason_type,remark,occurred_at)\n"
            "       VALUES(:eid,:id,'manual_progress','manual',:actor,:event_key,CAST(:"
            "before AS jsonb),CAST(:after AS jsonb),:reason,:remark,now())"
        ),
        {
            **values,
            "eid": uuid4(),
            "event_key": f"manual:{updated}",
            "before": json.dumps(before, ensure_ascii=False),
            "after": json.dumps(after, ensure_ascii=False),
        },
    )
    db.commit()
    return after
