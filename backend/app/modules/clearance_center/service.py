"""Clearance applications and approval transitions; no Walmart execution side effects."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.api import ApiError, ErrorCode
from app.modules.approvals.service import ApprovalService, signature
from app.modules.clearance_center.repository import ClearanceReadRepository
from app.modules.clearance_center.rules import RULE_VERSION, validate_rules
from app.modules.clearance_center.schemas import ApplicationWrite, DecisionWrite, ProgressWrite, RuleWrite


def fail(status: int = 409) -> None:
    raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=status)


class ClearanceService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = ClearanceReadRepository(session)
        self.approvals = ApprovalService(session)

    @staticmethod
    def _key(row: dict) -> tuple[str, str, str]:
        return (str(row["source_account_ref"]), str(row["store_id"]), str(row["item_id"]))

    def _request(self, rid: UUID | str, accounts: frozenset[str], *, lock: bool = False) -> dict:
        sql = """select * from ops_clearance_requests where id=cast(:id as uuid)
                 and source_account_ref=any(:accounts)"""
        if lock:
            sql += " for update"
        found = self.session.execute(text(sql), {"id": str(rid), "accounts": list(accounts)}).mappings().first()
        if not found:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        return dict(found)

    @staticmethod
    def _serialize(row: dict) -> dict:
        data = {}
        for name, value in row.items():
            if isinstance(value, (datetime, Decimal, UUID)):
                data[name] = str(value)
            else:
                data[name] = value
        return data

    def listing_detail(self, listing_id: str, accounts: frozenset[str]) -> dict:
        try:
            UUID(listing_id)
        except ValueError:
            fail(422)
        listing = self.repo.listing(listing_id, accounts)
        if not listing:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        rules, version = self.repo.rules(listing["source_account_ref"])
        metrics = self.repo.evidence([listing])[self._key(listing)]
        evaluation = self.repo.evaluated(listing, metrics, rules)
        return {"listing": self._serialize(listing), "evaluation": evaluation,
                "rule_config_version": version}

    def list_listings(self, accounts: frozenset[str], *, store_id: str = "",
                      keyword: str = "", eligible_only: bool = False,
                      risk_level: str | None = None,
                      candidate_status: str | None = None,
                      page: int = 1, page_size: int = 50) -> dict:
        listings = self.repo.listings(accounts, store_id=store_id, keyword=keyword,
                                      eligible_only=eligible_only)
        evidence = self.repo.evidence(listings)
        rule_cache: dict[str, tuple[dict, int]] = {}
        rows: list[dict] = []
        for listing in listings:
            account = listing["source_account_ref"]
            if account not in rule_cache:
                rule_cache[account] = self.repo.rules(account)
            rules, version = rule_cache[account]
            ev = self.repo.evaluated(listing, evidence[self._key(listing)], rules)
            if risk_level and ev["risk_level"] != risk_level:
                continue
            if candidate_status and ev["candidate_status"] != candidate_status:
                continue
            rows.append({"listing": self._serialize(listing), "evaluation": ev,
                         "rule_config_version": version})
        risk_rank = {"high": 0, "medium": 1, "unknown": 2, "low": 3}
        rows.sort(key=lambda x: (
            risk_rank.get(x["evaluation"]["risk_level"], 4),
            -(Decimal(x["evaluation"]["stock_capital_usd"])
              if x["evaluation"]["stock_capital_usd"] is not None else Decimal("-1")),
            -(x["evaluation"]["coverage_days"] or -1),
            x["listing"]["source_account_ref"], x["listing"]["store_id"], x["listing"]["item_id"]
        ))
        start = (page - 1) * page_size
        return {"items": rows[start:start + page_size], "total": len(rows),
                "page": page, "page_size": page_size}

    def summary(self, accounts: frozenset[str], store_id: str = "") -> dict:
        listing = self.list_listings(accounts, store_id=store_id, page=1, page_size=100000000)
        result = {"total": listing["total"], "high": 0, "medium": 0, "observe": 0,
                  "review_required": 0, "eligible_manual": 0}
        for x in listing["items"]:
            e = x["evaluation"]
            if e["candidate_status"] == "auto":
                if e["risk_level"] == "high":
                    result["high"] += 1
                elif e["risk_level"] == "medium":
                    result["medium"] += 1
            elif e["candidate_status"] == "observe":
                result["observe"] += 1
            elif e["candidate_status"] == "review_required":
                result["review_required"] += 1
            l = x["listing"]
            if (l.get("snapshot_wfs_available") is not None
                and Decimal(str(l["snapshot_wfs_available"])) > 0
                and l.get("wfs_available_quantity") is not None
                and Decimal(str(l["wfs_available_quantity"])) > 0
                and e.get("current_wfs_available")
                and "WFS_STOCK_UNAVAILABLE_OR_STALE" not in e["warnings"]):
                result["eligible_manual"] += 1
        return result

    def list_requests(self, accounts: frozenset[str], *, status: str | None = None,
                      store_id: str = "", page: int = 1, page_size: int = 50) -> dict:
        where = ["source_account_ref=any(:accounts)"]
        params = {"accounts": list(accounts), "limit": page_size,
                  "offset": (page - 1) * page_size}
        if status:
            where.append("status=:status")
            params["status"] = status
        if store_id:
            where.append("store_id=:store")
            params["store"] = store_id
        cond = " and ".join(where)
        total = self.session.execute(text(f"select count(*) from ops_clearance_requests where {cond}"),
                                     params).scalar_one()
        rows = self.session.execute(text(f"""select * from ops_clearance_requests where {cond}
             order by created_at desc,id limit :limit offset :offset"""), params).mappings().all()
        return {"items": [self._serialize(dict(x)) for x in rows], "total": int(total),
                "page": page, "page_size": page_size}

    def request_detail(self, rid: UUID, accounts: frozenset[str]) -> dict:
        row = self._request(rid, accounts)
        listing = self.listing_detail(str(row["listing_id"]), accounts)
        events = self.session.execute(text("""select event_type,actor_id,note,created_at
           from app_approval_events where approval_id=:id order by created_at,id"""),
           {"id": str(row["approval_id"])}).mappings().all()
        return {"request": self._serialize(row), "current": listing,
                "events": [self._serialize(dict(e)) for e in events]}

    def submit(self, payload: ApplicationWrite, accounts: frozenset[str], actor: str) -> dict:
        if len(set(payload.methods)) != len(payload.methods):
            fail(422)
        try:
            listing_id = str(UUID(payload.listing_id))
        except ValueError:
            fail(422)
        listing = self.repo.listing(listing_id, accounts, lock=True)
        if listing is None:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        if (listing["wfs_available_quantity"] is None or listing["wfs_available_quantity"] <= 0
            or listing["snapshot_wfs_available"] is None
            or listing["snapshot_wfs_available"] <= 0):
            fail()
        inventory_at = listing.get("inventory_captured_at")
        if (not inventory_at or not inventory_at.tzinfo or
            not timedelta(0) <= datetime.now(UTC) - inventory_at <= timedelta(hours=72)):
            fail()
        available = min(Decimal(str(listing["wfs_available_quantity"])),
                        Decimal(str(listing["snapshot_wfs_available"])))
        if payload.target_qty > available:
            fail()
        active = self.session.execute(text("""select 1 from ops_clearance_requests
          where source_account_ref=:account and store_id=:store and item_id=:item
            and status in ('pending','approved','running','paused') limit 1"""),
          {"account": listing["source_account_ref"], "store": listing["store_id"],
           "item": listing["item_id"]}).first()
        if active:
            fail()
        rule, config_version = self.repo.rules(listing["source_account_ref"])
        evidence = self.repo.evidence([listing])[self._key(listing)]
        evaluation = self.repo.evaluated(listing, evidence, rule)
        policy = self.session.execute(text("""select required_steps from app_approval_rules
            where approval_type='clearance_request' and is_active=true""")).mappings().first()
        if policy is None or policy["required_steps"] != 1:
            fail()
        now = datetime.now(UTC)
        rid = str(uuid4())
        aid = str(uuid4())
        snapshot = {
            "source": {"clearance_request_id": rid,
                       "listing_identity": list(self._key(listing)),
                       "target_qty": payload.target_qty,
                       "methods": payload.methods,
                       "rule_version": RULE_VERSION, "rule_config_version": config_version},
            "approval_policy": {"required_steps": 1},
        }
        risk = evaluation["risk_level"]
        if risk not in ("high", "medium"):
            risk = "low"
        try:
            self.session.execute(text("""
              insert into app_approval_requests
                (id,approval_type,business_ref,source_account_ref,applicant_id,title,
                 reason,evidence,status,risk_level,snapshot,snapshot_hash,submitted_at,updated_at)
              values (cast(:id as uuid),'clearance_request',:ref,:account,:actor,:title,
                      :reason,:evidence,'submitted',:risk,cast(:snapshot as jsonb),:hash,:now,:now)
            """), {"id": aid, "ref": rid, "account": listing["source_account_ref"],
                   "actor": actor, "title": "清货申请 · " + str(listing["item_id"]),
                   "reason": payload.reason, "evidence": payload.remark,
                   "risk": risk, "snapshot": json.dumps(snapshot, ensure_ascii=False),
                   "hash": signature(snapshot), "now": now})
            self.session.execute(text("""
              insert into ops_clearance_requests
                (id,listing_id,source_account_ref,store_id,item_id,requester_id,
                 target_qty,methods,reason,remark,due_date,proposed_price,
                 source,risk_level,rule_version,status,approval_id)
              values (cast(:id as uuid),cast(:listing_id as uuid),:account,:store,:item,
                      :requester,:qty,cast(:methods as jsonb),:reason,:remark,:due,
                      :price,:source,:risk,:rule,'pending',cast(:approval as uuid))
            """), {"id": rid, "listing_id": listing_id, "account": listing["source_account_ref"],
                   "store": listing["store_id"], "item": listing["item_id"],
                   "requester": actor, "qty": payload.target_qty,
                   "methods": json.dumps(payload.methods, ensure_ascii=False),
                   "reason": payload.reason, "remark": payload.remark,
                   "due": payload.due_date, "price": payload.proposed_price,
                   "source": payload.source, "risk": risk,
                   "rule": RULE_VERSION, "approval": aid})
            self.approvals._event(aid, "submitted", actor, payload.remark,
                                  {"clearance_request_id": rid, "executed": False})
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            fail()
        return {"request_id": rid, "approval_id": aid, "status": "pending"}

    def withdraw(self, rid: UUID, accounts: frozenset[str], actor: str) -> dict:
        row = self._request(rid, accounts, lock=True)
        if row["status"] != "pending" or row["requester_id"] != actor:
            fail()
        self.session.execute(text("""update ops_clearance_requests
            set status='withdrawn',version=version+1,updated_at=now()
            where id=:id and status='pending'"""), {"id": str(rid)})
        self.session.execute(text("""update app_approval_requests
            set status='withdrawn',version=version+1,updated_at=now()
            where id=:id and status='submitted'"""), {"id": str(row["approval_id"])})
        self.approvals._event(str(row["approval_id"]), "withdrawn", actor,
                              "申请撤回", {"executed": False})
        self.session.commit()
        return {"status": "withdrawn"}

    def decide(self, aid: UUID, payload: DecisionWrite, accounts: frozenset[str], actor: str) -> dict:
        if payload.decision == "rejected" and not payload.note:
            fail(422)
        record = self.approvals._record(aid, accounts, lock=True)
        if (record["approval_type"] != "clearance_request" or
            record["status"] != "submitted" or
            record["version"] != payload.expected_version or
            record["applicant_id"] == actor):
            fail()
        row = self._request(record["business_ref"], accounts, lock=True)
        if row["status"] != "pending" or row["approval_id"] != aid:
            fail()
        current = self.repo.listing(str(row["listing_id"]), accounts, lock=True)
        if current is None:
            fail()
        if payload.decision == "approved":
            captured_at = current.get("inventory_captured_at")
            if (not captured_at or not captured_at.tzinfo or
                not timedelta(0) <= datetime.now(UTC) - captured_at <= timedelta(hours=72)
                or current["snapshot_wfs_available"] is None
                or current["wfs_available_quantity"] is None
                or min(current["snapshot_wfs_available"], current["wfs_available_quantity"]) < row["target_qty"]):
                fail()
            self.session.execute(text("""
              insert into app_approval_step_decisions
                (id,approval_id,step_number,reviewer_id,decision,note)
              values (cast(:id as uuid),:approval,1,:actor,'approved',:note)
            """), {"id": str(uuid4()), "approval": str(aid), "actor": actor,
                   "note": payload.note or None})
        updated = self.session.execute(text("""
          update app_approval_requests set status=:status,version=version+1,
            reviewed_by=:actor,reviewed_at=now(),review_note=:note,updated_at=now()
          where id=:id and version=:version and status='submitted'
        """), {"status": payload.decision, "actor": actor, "note": payload.note,
               "id": str(aid), "version": payload.expected_version})
        if updated.rowcount != 1:
            fail()
        self.session.execute(text("""
          update ops_clearance_requests set status=:status,version=version+1,updated_at=now()
          where id=:id and status='pending'
        """), {"status": payload.decision, "id": str(row["id"])})
        self.approvals._event(str(aid), payload.decision, actor, payload.note,
                              {"clearance_request_id": str(row["id"]), "executed": False})
        self.session.commit()
        return {"updated": True, "status": payload.decision,
                "request_id": str(row["id"])}

    def progress(self, rid: UUID, payload: ProgressWrite, accounts: frozenset[str],
                 actor: str) -> dict:
        row = self._request(rid, accounts, lock=True)
        if row["status"] not in ("approved", "running", "paused"):
            fail()
        before = (row["sold_qty"], row["removed_qty"], row["disposed_qty"])
        values = (payload.sold_qty, payload.removed_qty, payload.disposed_qty)
        if (row["version"] != payload.expected_version or
            any(a < b for a, b in zip(values, before)) or
            sum(values) > row["target_qty"]):
            fail()
        status = "done" if sum(values) == row["target_qty"] else ("paused" if row["status"] == "paused" else "running")
        self.session.execute(text("""
           update ops_clearance_requests set sold_qty=:sold,removed_qty=:removed,
             disposed_qty=:disposed,status=:status,version=version+1,updated_at=now()
           where id=:id and version=:version
        """), {"sold": values[0], "removed": values[1], "disposed": values[2],
               "status": status, "id": str(rid), "version": payload.expected_version})
        self.approvals._event(str(row["approval_id"]), "progress_updated", actor, "",
                              {"sold": values[0], "removed": values[1],
                               "disposed": values[2], "executed": False})
        self.session.commit()
        return {"status": status, "version": row["version"] + 1}

    def set_pause(self, rid: UUID, accounts: frozenset[str], actor: str, paused: bool) -> dict:
        row = self._request(rid, accounts, lock=True)
        if (paused and row["status"] not in ("running", "approved")) or (
            not paused and row["status"] != "paused"
        ):
            fail()
        status = "paused" if paused else "running"
        self.session.execute(text("""update ops_clearance_requests
            set status=:status,version=version+1,updated_at=now() where id=:id"""),
            {"status": status, "id": str(rid)})
        self.approvals._event(str(row["approval_id"]), status, actor, "",
                              {"executed": False})
        self.session.commit()
        return {"status": status}

    def update_rules(self, payload: RuleWrite, accounts: frozenset[str], actor: str) -> dict:
        if payload.source_account_ref not in accounts:
            raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED, status_code=403)
        try:
            merged = validate_rules(payload.rules)
        except ValueError:
            fail(422)
        row = self.session.execute(text("""
          select version from ops_clearance_rule_sets where source_account_ref=:account for update
        """), {"account": payload.source_account_ref}).mappings().first()
        version = int(row["version"]) if row else 0
        if version != payload.expected_version:
            fail()
        next_version = version + 1
        self.session.execute(text("""
          insert into ops_clearance_rule_sets(source_account_ref,version,rules_json,updated_by)
          values(:account,:version,cast(:rules as jsonb),:actor)
          on conflict(source_account_ref) do update set
            version=excluded.version,rules_json=excluded.rules_json,
            updated_by=excluded.updated_by,updated_at=now()
        """), {"account": payload.source_account_ref, "version": next_version,
               "rules": json.dumps(merged, ensure_ascii=False), "actor": actor})
        self.session.execute(text("""
          insert into ops_clearance_rule_events(id,source_account_ref,version,rules_json,actor_id)
          values(cast(:id as uuid),:account,:version,cast(:rules as jsonb),:actor)
        """), {"id": str(uuid4()), "account": payload.source_account_ref,
               "version": next_version, "rules": json.dumps(merged, ensure_ascii=False),
               "actor": actor})
        self.session.commit()
        return {"version": next_version, "rules": merged}
