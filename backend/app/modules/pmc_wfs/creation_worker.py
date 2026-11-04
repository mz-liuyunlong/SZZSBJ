"""Durable execution boundary: uncertain writes are read back, never blindly re-sent.

Per planned shipment (ticket), Rocky 2026-11-04:

* Walmart refuses, or the request provably never left -> FAILED with the reason; boxes freed.
* Walmart answers with the shipment -> SUCCEEDED, labels fetched.
* Our order id (Walmart ``inboundOrderId``) follows 8088: ``PMC-<店铺码>-<YYYYMMDD>-<序号>``,
  assigned once before the first submission and kept for every retry / read-back.
* Same call order as the 14 real 8088 creations (2026-10-14..16): look the order id up first
  (only send when Walmart has nothing under it; an id already used elsewhere moves to the next
  number), POST, then read back right away -- the destination FC (``fcName``) only comes back
  in the read-back, never in the create response.
* No trustworthy answer (timeout, 5xx, accepted without ids) -> stays RUNNING ("提交中") and
  is read back by our order id every 3 minutes, at most 10 times; still not
  found after the 10th read -> FAILED ("查询超时"), boxes freed.
* Nothing here schedules itself: the 数据中心 · 任务中心 task 「WFS 创建结果拉取」
  (``creation_task``) runs every 3 minutes and calls ``run_operation`` for what is due.
* Retry (FAILED only) first reads back by the same order id; only if Walmart has nothing is
  the same order sent again, so one batch of boxes can never become two shipments.
"""

import base64
import re
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select

from app.modules.pmc_wfs.creation_config import POLL_INTERVAL_SECONDS, POLL_MAX_ATTEMPTS
from app.modules.pmc_wfs.creation_models import (
    WfsBoxHold,
    WfsCreation,
    WfsCreationEvent,
    WfsCreationTicket,
)
from app.modules.pmc_wfs.creation_service import guard_write, manually_approved
from app.modules.pmc_wfs.walmart_gateway import DefinitiveRejection, NotSent, ResultUnknown

__all__ = ["DefinitiveRejection", "next_order_id", "order_ref", "run_operation", "shipments_of"]

ORDER_ZONE = ZoneInfo("Asia/Shanghai")
ORDER_ID_TRIES = 5  # numbers skipped when Walmart already has the id (e.g. made on 8088)
_STORE_CODE = re.compile(r"^[A-Z0-9]{2,12}$")


def order_ref(ticket) -> str:
    """Walmart inboundOrderId of a ticket (tickets from before 0080 used the ticket id)."""
    return ticket.inbound_order_id or str(ticket.id)


def next_order_id(session, store_code: str, today: date | None = None) -> str:
    """8088 format ``PMC-<店铺码>-<YYYYMMDD>-<NN>``: next free number for that store and day."""
    code = (store_code or "").strip().upper()
    if not _STORE_CODE.fullmatch(code):
        raise NotSent("WFS_STORE_CODE_INVALID", f"店铺码不合法：{store_code or '空'}")
    day = (today or datetime.now(ORDER_ZONE).date()).strftime("%Y%m%d")
    prefix = f"PMC-{code}-{day}-"
    used = session.scalars(
        select(WfsCreationTicket.inbound_order_id).where(
            WfsCreationTicket.inbound_order_id.like(prefix + "%")
        )
    )
    numbers = [int(v[len(prefix) :]) for v in used if v[len(prefix) :].isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1:02d}"


def _store_code(gateway, snapshot) -> str:
    code_of = getattr(gateway, "store_code", None)
    return code_of(snapshot) if code_of else ""


TIMEOUT_REASON = (
    f"已每 {POLL_INTERVAL_SECONDS // 60} 分钟查询一次、共 {POLL_MAX_ATTEMPTS} 次，"
    "仍未在 Walmart 查到这票货件，按失败处理"
)


def shipments_of(values) -> list[dict]:
    """Adapter result -> verified shipment records (ids unique, bounded)."""
    if not isinstance(values, list) or len(values) > 5000:
        raise ValueError("unverified shipment result")
    records = []
    for value in values:
        record = {"shipment_id": value} if isinstance(value, str) else dict(value)
        sid = record.get("shipment_id")
        if not isinstance(sid, str) or not sid.strip() or len(sid) > 128:
            raise ValueError("unverified shipment result")
        records.append(record)
    if len({r["shipment_id"] for r in records}) != len(records):
        raise ValueError("unverified shipment result")
    return records


# Kept for callers that only need ids.
def actual_ids(values):
    records = shipments_of(values)
    if not records:
        raise ValueError("unverified shipment result")
    return [r["shipment_id"] for r in records]


def _event(session, ident, kind, **evidence):
    session.add(
        WfsCreationEvent(operation_id=ident, actor_uid="wfs-worker", kind=kind, evidence=evidence)
    )


def _snapshot(op, ticket):
    return {
        **op.snapshot,
        "approval_ref": op.approval_ref,
        "ticket_boxes": ticket.allocation.get("boxes"),
    }


def release_holds(session, ident, ticket, reason_code):
    """Failed or rejected: the ticket's boxes go back to the packing order."""
    count = session.scalar(
        select(func.count()).select_from(WfsBoxHold).where(WfsBoxHold.ticket_id == ticket.id)
    )
    if count:
        session.execute(delete(WfsBoxHold).where(WfsBoxHold.ticket_id == ticket.id))
        _event(
            session,
            ident,
            "holds_released",
            ticket_id=str(ticket.id),
            boxes=count,
            reason=reason_code,
        )
    return count


def _fail(session, ident, ticket, code, reason):
    ticket.state, ticket.error_code = "FAILED", code[:64]
    result = {k: v for k, v in ticket.result.items() if k != "polling"}
    ticket.result = {
        **result,
        "error_message": reason[:500],
        "failed_at": datetime.now(UTC).isoformat(),
    }
    _event(session, ident, "failed", ticket_id=str(ticket.id), code=code, reason=reason[:500])
    release_holds(session, ident, ticket, code)


def _succeed(session, ident, ticket, records):
    shipments = {r["shipment_id"]: r for r in records}
    ticket.state, ticket.error_code = "SUCCEEDED", None
    drop = ("polling", "error_message", FC_CHECK)
    result = {k: v for k, v in ticket.result.items() if k not in drop}
    labels = dict(result.get("labels", {}))
    for sid in shipments:
        labels.setdefault(sid, {"state": "PENDING"})
    if _missing_fc(list(shipments.values())):
        # Read back again on the 3-minute task until Walmart shows the FC (at most 10 times).
        result[FC_CHECK] = _next_check({"count": 0, "max": POLL_MAX_ATTEMPTS})
    ticket.result = {
        **result,
        "shipments": shipments,
        "labels": labels,
        "succeeded_at": datetime.now(UTC).isoformat(),
    }
    _event(session, ident, "succeeded", ticket_id=str(ticket.id), shipments=sorted(shipments))


FC_CHECK = "fc_check"


def _next_check(check):
    at = datetime.now(UTC) + timedelta(seconds=POLL_INTERVAL_SECONDS)
    return {**check, "next_at": at.isoformat()}


def fc_check_due(result, now=None) -> bool:
    """A created ticket whose destination FC is still unknown and due for a read-back."""
    check = result.get(FC_CHECK)
    return bool(check) and poll_due(check, now)


def _start_polling(session, ident, ticket, code):
    now = datetime.now(UTC)
    ticket.state, ticket.error_code = "RUNNING", code[:64] if code else None
    ticket.result = {
        **ticket.result,
        "polling": {
            "count": 0,
            "max": POLL_MAX_ATTEMPTS,
            "next_at": (now + timedelta(seconds=POLL_INTERVAL_SECONDS)).isoformat(),
            "since": now.isoformat(),
        },
    }
    _event(session, ident, "polling_started", ticket_id=str(ticket.id), code=code)
    return True


def run_operation(factory, gateway, ident, action="execute") -> bool:
    """Run one action for one operation; returns True while a ticket still waits for a
    read-back. Called by the task-center task (``creation_task``) or an isolated test."""
    ident = UUID(str(ident))
    with factory() as session:
        guard_write(session)
        op = session.get(WfsCreation, ident)
        if op is None:
            return False
        if not manually_approved(op):
            # Red line: no Walmart call (create, read-back or label) without a written
            # human approval for this operation. Record the refusal, touch nothing else.
            _event(session, ident, "refused_unapproved", action=action, state=op.state)
            session.commit()
            return False
        if action in ("execute", "retry"):
            gateway.validate(op.snapshot)
        ticket_ids = list(
            session.scalars(
                select(WfsCreationTicket.id)
                .where(WfsCreationTicket.operation_id == ident)
                .order_by(WfsCreationTicket.number)
            )
        )
    poll_again = False
    for ticket_id in ticket_ids:
        poll_again |= execute_ticket(factory, gateway, ident, ticket_id, action)
    with factory() as session:
        op = session.scalar(select(WfsCreation).where(WfsCreation.id == ident).with_for_update())
        states = list(
            session.scalars(
                select(WfsCreationTicket.state).where(WfsCreationTicket.operation_id == ident)
            )
        )
        if states and all(s == "SUCCEEDED" for s in states):
            op.state = "SUCCEEDED"
        elif "RUNNING" in states:
            op.state = "RUNNING"
        elif "UNKNOWN" in states:
            op.state = "UNKNOWN"
        elif "QUEUED" in states:
            op.state = "QUEUED"  # approved, not yet executed
        elif "SUCCEEDED" in states:
            op.state = "PARTIAL"
        else:
            op.state = "FAILED"
        session.commit()
    return poll_again


POLL_GRACE = timedelta(seconds=30)


def poll_due(polling, now=None) -> bool:
    """A 3-minute task run may start a few seconds before ``next_at``; allow 30 s."""
    next_at = polling.get("next_at")
    if not next_at:
        return True
    return datetime.fromisoformat(next_at) <= (now or datetime.now(UTC)) + POLL_GRACE


def _claim(factory, gateway, ident, ticket_id, action):
    """Decide under the ticket row lock what this run does; returns (mode, snapshot, ...)."""
    with factory() as session:
        ticket = session.scalar(
            select(WfsCreationTicket).where(WfsCreationTicket.id == ticket_id).with_for_update()
        )
        op = session.get(WfsCreation, ident)
        if not manually_approved(op):
            return None
        polling = ticket.result.get("polling")
        mode = None
        if ticket.state == "QUEUED" and action in ("execute", "retry", "reconcile"):
            mode = "create"
        elif ticket.state == "RUNNING" and polling and action == "poll":
            if not poll_due(polling):
                return None  # read back every 3 minutes, not on every task run
            mode = "poll"
        elif ticket.state in ("RUNNING", "UNKNOWN") and action == "reconcile":
            started = ticket.result.get("started_at")
            if ticket.state == "RUNNING" and not polling and started:
                if datetime.now(UTC) - datetime.fromisoformat(started) < timedelta(minutes=10):
                    return None  # a worker is still inside the create call
            mode = "check"
        elif ticket.state == "SUCCEEDED":
            return ("labels", _snapshot(op, ticket), ticket.allocation, None, order_ref(ticket))
        if mode is None:
            return None
        attempt = str(uuid4())
        if mode == "create":
            if ticket.inbound_order_id is None:
                try:
                    ticket.inbound_order_id = next_order_id(
                        session, _store_code(gateway, op.snapshot)
                    )
                except NotSent as error:
                    _fail(session, ident, ticket, error.code, error.reason)
                    session.commit()
                    return None
            submissions = int(ticket.result.get("submissions", 0))
            ticket.result = {
                **{k: v for k, v in ticket.result.items() if k != "error_message"},
                "started_at": datetime.now(UTC).isoformat(),
                "attempt": attempt,
                "submissions": submissions + 1,
            }
            ticket.state, ticket.error_code = "RUNNING", None
            op.state = "RUNNING"
            _event(
                session,
                ident,
                "started_create",
                ticket_id=str(ticket_id),
                submission=submissions + 1,
                inbound_order_id=ticket.inbound_order_id,
            )
            mode = "resubmit" if submissions else "create"
        else:
            ticket.result = {**ticket.result, "attempt": attempt}
        session.commit()
        return (mode, _snapshot(op, ticket), ticket.allocation, attempt, order_ref(ticket))


def _next_number(factory, gateway, ident, ticket_id, attempt, taken):
    """Walmart already has ``taken`` (not ours: we never sent it) -> the next free number."""
    with factory() as session:
        ticket = session.scalar(
            select(WfsCreationTicket).where(WfsCreationTicket.id == ticket_id).with_for_update()
        )
        if ticket.result.get("attempt") != attempt:
            return None
        op = session.get(WfsCreation, ident)
        ticket.inbound_order_id = next_order_id(session, _store_code(gateway, op.snapshot))
        skipped = [*ticket.result.get("skipped_order_ids", []), taken][-ORDER_ID_TRIES:]
        ticket.result = {**ticket.result, "skipped_order_ids": skipped}
        _event(
            session,
            ident,
            "order_id_taken",
            ticket_id=str(ticket_id),
            taken=taken,
            next=ticket.inbound_order_id,
        )
        session.commit()
        return ticket.inbound_order_id


def _precheck(factory, gateway, ident, ticket_id, attempt, order, snapshot):
    """Before the first POST (8088 did this every time): send only if Walmart has nothing
    under the order id. Returns (order, None) to go on, or (order, (code, reason)) to stop
    without sending anything."""
    for _ in range(ORDER_ID_TRIES):
        try:
            found = gateway.reconcile(order, snapshot)
        except Exception as error:
            code = getattr(error, "code", None) or "WFS_PRECHECK_FAILED"
            return order, (
                "WFS_PRECHECK_FAILED",
                f"提交前去 Walmart 查单号没有成功（{code}），未提交；可以点重试",
            )
        if not found:
            return order, None
        try:
            order = _next_number(factory, gateway, ident, ticket_id, attempt, order)
        except NotSent as error:
            return order, (error.code, error.reason)
        if order is None:
            return order, ("WFS_ATTEMPT_SUPERSEDED", "这票已被另一次运行接手")
    return order, (
        "WFS_ORDER_ID_CONFLICT",
        f"连续 {ORDER_ID_TRIES} 个单号在 Walmart 已存在，未提交；请联系管理员",
    )


def _merge_readback(records, found):
    """Create response + read-back: FC / address / status from the read-back, cartons kept."""
    if not found:
        return records
    by_id = {r["shipment_id"]: dict(r) for r in records}
    for row in found:
        base = by_id.setdefault(row["shipment_id"], {"shipment_id": row["shipment_id"]})
        for key, value in row.items():
            if value not in (None, {}, "") and (key != "cartons" or not base.get("cartons")):
                base[key] = value
    return list(by_id.values())


def _missing_fc(records) -> bool:
    return any(not (r.get("fc") if isinstance(r, dict) else None) for r in records)


def execute_ticket(factory, gateway, ident, ticket_id, action) -> bool:
    """Run one ticket; returns True when a later poll must be scheduled."""
    claimed = _claim(factory, gateway, ident, ticket_id, action)
    if claimed is None:
        return False
    mode, snapshot, allocation, attempt, order = claimed
    if mode == "labels":
        _labels(factory, gateway, ident, ticket_id, snapshot)
        return False
    outcome, payload = None, None
    if mode == "create":
        order, stop = _precheck(factory, gateway, ident, ticket_id, attempt, order, snapshot)
        if stop is not None:
            outcome, payload = "precheck", stop
    if mode == "resubmit":
        # Retry: ask Walmart first whether our order id already exists.
        try:
            found = gateway.reconcile(order, snapshot)
            if found:
                outcome, payload = "ok", shipments_of(found)
        except Exception as error:
            outcome, payload = "unknown", getattr(error, "code", "WFS_RESULT_UNKNOWN")
    if outcome is None and mode in ("create", "resubmit"):
        try:
            records = shipments_of(gateway.create(order, snapshot, allocation))
            outcome, payload = ("ok", records) if records else ("unknown", "WFS_ACCEPTED")
        except DefinitiveRejection as error:
            outcome, payload = "rejected", (error.code, error.reason or "Walmart 拒绝了请求")
        except NotSent as error:
            outcome, payload = "not_sent", (error.code, error.reason or error.code)
        except ResultUnknown as error:
            outcome, payload = "unknown", error.code
        except Exception:
            # No response, malformed result and process/network ambiguity keep all holds.
            outcome, payload = "unknown", "WFS_RESULT_UNKNOWN"
        if outcome == "ok" and _missing_fc(payload):
            # 8088: the create answer has no fcName; the read-back right after does.
            try:
                found = shipments_of(gateway.reconcile(order, snapshot) or [])
                payload = _merge_readback(payload, found)
            except Exception:
                pass  # created anyway; the 3-minute task fills the FC in later
    if mode in ("poll", "check"):
        try:
            found = gateway.reconcile(order, snapshot)
            outcome, payload = ("ok", shipments_of(found)) if found else ("missing", None)
        except Exception as error:
            outcome, payload = "missing", getattr(error, "code", "WFS_RESULT_UNKNOWN")
    poll_again = False
    with factory() as session:
        ticket = session.scalar(
            select(WfsCreationTicket).where(WfsCreationTicket.id == ticket_id).with_for_update()
        )
        if ticket.result.get("attempt") != attempt:
            return False  # A newer run owns this ticket; do not overwrite it.
        if outcome == "ok":
            _succeed(session, ident, ticket, payload)
            _resolve(gateway, order, "ok", "read back / created")
        elif outcome == "precheck":
            # Nothing was sent: this does not count as a submission.
            ticket.result = {
                **ticket.result,
                "submissions": max(int(ticket.result.get("submissions", 1)) - 1, 0),
            }
            if payload[0] != "WFS_ATTEMPT_SUPERSEDED":
                _fail(session, ident, ticket, *payload)
        elif outcome in ("rejected", "not_sent"):
            _fail(session, ident, ticket, *payload)
        elif outcome == "unknown":
            poll_again = _start_polling(session, ident, ticket, payload)
        elif outcome == "missing" and mode == "poll":
            polling = dict(ticket.result["polling"])
            polling["count"] += 1
            polling["last_checked_at"] = datetime.now(UTC).isoformat()
            if payload:
                polling["last_error"] = payload
            if polling["count"] >= polling.get("max", POLL_MAX_ATTEMPTS):
                ticket.result = {**ticket.result, "polling": polling}
                _fail(session, ident, ticket, "WFS_RESULT_TIMEOUT", TIMEOUT_REASON)
                _resolve(gateway, order, "failed", "not found after polling")
            else:
                polling["next_at"] = (
                    datetime.now(UTC) + timedelta(seconds=POLL_INTERVAL_SECONDS)
                ).isoformat()
                ticket.result = {**ticket.result, "polling": polling}
                _event(session, ident, "polled", ticket_id=str(ticket_id), count=polling["count"])
                poll_again = True
        elif outcome == "missing" and mode == "check" and ticket.state == "UNKNOWN":
            # A pre-polling UNKNOWN ticket joins the regular 3-minute schedule.
            poll_again = _start_polling(session, ident, ticket, payload or "WFS_RESULT_UNKNOWN")
        session.commit()
        succeeded = ticket.state == "SUCCEEDED"
    if succeeded:
        _labels(factory, gateway, ident, ticket_id, snapshot)
    return poll_again


def _resolve(gateway, ticket_id, outcome, note):
    resolve = getattr(gateway, "resolve", None)
    if resolve is not None:
        resolve(str(ticket_id), outcome, note)


def _refresh_fc(session, gateway, ident, ticket, snapshot, check):
    """Created, but the FC was not in the answers yet: read back by our order id once more."""
    shipments = dict(ticket.result.get("shipments", {}))
    try:
        found = shipments_of(gateway.reconcile(order_ref(ticket), snapshot) or [])
    except Exception:
        found = []
    merged = {r["shipment_id"]: r for r in _merge_readback(list(shipments.values()), found)}
    count = int(check.get("count", 0)) + 1
    result = {**ticket.result, "shipments": merged}
    if not _missing_fc(list(merged.values())) or count >= int(check.get("max", POLL_MAX_ATTEMPTS)):
        result.pop(FC_CHECK, None)
    else:
        result[FC_CHECK] = _next_check({**check, "count": count})
    ticket.result = result
    _event(
        session,
        ident,
        "fc_read_back",
        ticket_id=str(ticket.id),
        count=count,
        fcs={sid: r.get("fc") for sid, r in merged.items()},
    )


def _labels(factory, gateway, ident, ticket_id, snapshot):
    # Serializing label retrieval on the ticket prevents concurrent retries overwriting results.
    with factory() as session:
        ticket = session.scalar(
            select(WfsCreationTicket).where(WfsCreationTicket.id == ticket_id).with_for_update()
        )
        if ticket.state != "SUCCEEDED":
            return
        check = ticket.result.get(FC_CHECK)
        if check and poll_due(check):
            _refresh_fc(session, gateway, ident, ticket, snapshot, check)
        labels = dict(ticket.result.get("labels", {}))
        shipments = ticket.result.get("shipments", {})
        single = len(labels) == 1
        for sid, value in labels.items():
            if value["state"] == "READY":
                continue
            cartons = (shipments.get(sid) or {}).get("cartons") or (
                ticket.allocation.get("boxes") if single else None
            )
            try:
                pdf = gateway.label(sid, snapshot, cartons=cartons)
                if (
                    not isinstance(pdf, bytes)
                    or not pdf.startswith(b"%PDF-")
                    or len(pdf) > 10_000_000
                ):
                    raise ValueError("invalid label")
                labels[sid] = {"state": "READY", "pdf": base64.b64encode(pdf).decode("ascii")}
            except Exception:
                labels[sid] = {"state": "FAILED"}
        ticket.result = {**ticket.result, "labels": labels}
        _event(
            session,
            ident,
            "labels",
            ticket_id=str(ticket_id),
            states={sid: v["state"] for sid, v in labels.items()},
        )
        session.commit()
