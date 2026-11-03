"""WFS settings reads / writes (PRP ``PRPs/pmc-wfs-settings.md`` §5).

Rules: append-only versions; ``get_effective_rules(at)`` returns the version in force on a
day (the exception center reads it, PRP §7 step 4). FC list = FCs seen on the current
published board (Lingxing code / address), region = saved choice or the state default.
No external call; writes only the settings tables and the change log.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.api import ApiError
from app.modules.pmc_wfs.arrival_rules import region_of_state
from app.modules.pmc_wfs.lingxing_models import WfsBoardPublication, WfsShipmentBoardRow
from app.modules.pmc_wfs.settings_models import (
    WfsCreationDefaults,
    WfsFcRegion,
    WfsRuleSetting,
    WfsRuleSettingVersion,
    WfsSettingsChange,
)
from app.modules.pmc_wfs.settings_schemas import (
    ChangeQuery,
    CreationDefaultsOut,
    CreationDefaultsUpdate,
    FcRegionOut,
    FcRegionUpdate,
    LogisticsChannelOut,
    RuleRow,
    RuleSetOut,
    RuleVersionCreate,
    RuleVersionOut,
    SettingsChangeOut,
)
from app.modules.pmc_wfs.settings_seed import CREATION_DEFAULTS
from app.modules.pmc_wfs.source_models import LingxingLogisticsChannelOds, PmcWfsSourceFile


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _version_out(v: WfsRuleSettingVersion) -> RuleVersionOut:
    return RuleVersionOut(
        version_no=v.version_no,
        effective_date=v.effective_date,
        reason=v.reason,
        created_by=v.created_by,
        created_at=v.created_at,
    )


def _row_out(r: WfsRuleSetting) -> RuleRow:
    return RuleRow(
        rule_key=r.rule_key,
        node=r.node,
        region=r.region,
        carrier=r.carrier,
        channel=r.channel,
        days=r.days,
        remind_days=r.remind_days,
        row_effective_date=r.row_effective_date,
        notify=r.notify,
        remark=r.remark,
        decided=r.decided,
    )


_ZIP = re.compile(r"^\d{5}(-\d{4})?$")
_COUNTRY = {"US", "USA", "UNITED STATES", "美国"}


def parse_fc_address(
    address: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Lingxing ``distribution_addresses`` → (city, state, zip, full address).

    Real rows look like ``1 Test Ave,Chino,CA,美国,US,91708``; older ones put the ZIP before
    the country. The ZIP is whichever part looks like a US ZIP, country parts are dropped,
    and the last two remaining parts are city and state. The full address reads
    ``1 Test Ave, Chino, CA 91708``. Missing parts are ``None``."""
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    zips = [p for p in parts if _ZIP.match(p)]
    zip_code = zips[-1] if zips else None
    rest = [p for p in parts if not _ZIP.match(p) and p.upper() not in _COUNTRY]
    if len(rest) < 2:
        return None, None, zip_code, ", ".join(parts) or None
    city, state = rest[-2], rest[-1]
    tail = f"{state} {zip_code}" if zip_code else state
    return city, state, zip_code, ", ".join([*rest[:-2], city, tail])


def _region(value: str) -> Any:
    return value if value in ("美西", "美中", "美东") else "待定"


class WfsSettingsService:
    def __init__(self, session: Session, accounts: frozenset[str] = frozenset()) -> None:
        self.session = session
        self.accounts = accounts

    # ---- rules ----------------------------------------------------------------------

    def _rows(self, version: WfsRuleSettingVersion) -> list[RuleRow]:
        rows = self.session.scalars(
            select(WfsRuleSetting)
            .where(WfsRuleSetting.version_id == version.id)
            .order_by(WfsRuleSetting.row_no)
        )
        return [_row_out(r) for r in rows]

    def _ruleset(self, version: WfsRuleSettingVersion) -> RuleSetOut:
        rows = self._rows(version)
        return RuleSetOut(
            version=_version_out(version),
            rows=rows,
            sample_rows=sum(1 for r in rows if not r.decided),
        )

    def effective_version(self, at: date | None = None) -> WfsRuleSettingVersion:
        day = at or _utc_today()
        version = self.session.scalar(
            select(WfsRuleSettingVersion)
            .where(WfsRuleSettingVersion.effective_date <= day)
            .order_by(WfsRuleSettingVersion.version_no.desc())
            .limit(1)
        )
        if version is None:  # before the 8088 seed's date: the seed is the baseline
            version = self.session.scalar(
                select(WfsRuleSettingVersion).order_by(WfsRuleSettingVersion.version_no).limit(1)
            )
        if version is None:
            raise ApiError(code="WFS_SETTINGS_NOT_READY", status_code=503)
        return version

    def get_effective_rules(self, at: date | None = None) -> RuleSetOut:
        return self._ruleset(self.effective_version(at))

    def list_versions(self) -> list[RuleVersionOut]:
        versions = self.session.scalars(
            select(WfsRuleSettingVersion).order_by(WfsRuleSettingVersion.version_no.desc())
        )
        return [_version_out(v) for v in versions]

    def create_version(self, cmd: RuleVersionCreate, actor: str) -> RuleSetOut:
        if cmd.effective_date < _utc_today():
            raise ApiError(
                code="WFS_SETTINGS_EFFECTIVE_DATE_PAST",
                status_code=422,
                message="生效日不能早于今天",
            )
        before = self.get_effective_rules(cmd.effective_date)
        last = self.session.scalar(select(func.max(WfsRuleSettingVersion.version_no))) or 0
        version = WfsRuleSettingVersion(
            version_no=last + 1,
            effective_date=cmd.effective_date,
            reason=cmd.reason,
            created_by=actor,
        )
        self.session.add(version)
        self.session.flush()
        for i, row in enumerate(cmd.rows, start=1):
            self.session.add(WfsRuleSetting(version_id=version.id, row_no=i, **row.model_dump()))
        self._log(
            "rules",
            f"v{version.version_no}",
            {
                "version_no": before.version.version_no,
                "rows": before.model_dump(mode="json")["rows"],
            },
            {
                "version_no": version.version_no,
                "rows": [r.model_dump(mode="json") for r in cmd.rows],
            },
            cmd.reason,
            actor,
        )
        self.session.commit()
        return self._ruleset(version)

    # ---- FC regions -----------------------------------------------------------------

    def _board_fcs(self) -> dict[str, dict[str, Any]]:
        if not self.accounts:
            return {}
        pubs = select(WfsBoardPublication.id).where(
            WfsBoardPublication.source_account_ref.in_(sorted(self.accounts)),
            WfsBoardPublication.is_current.is_(True),
        )
        out: dict[str, dict[str, Any]] = {}
        rows = self.session.execute(
            select(WfsShipmentBoardRow.logistics_code, WfsShipmentBoardRow.payload_json).where(
                WfsShipmentBoardRow.publication_id.in_(pubs),
                WfsShipmentBoardRow.logistics_code.is_not(None),
            )
        )
        for code, payload in rows:
            address = ((payload or {}).get("cargo") or {}).get("distribution_addresses")
            city, state, zip_code, full = parse_fc_address(address)
            fc = out.setdefault(
                code, {"city": city, "state": state, "zip": zip_code, "address": full, "n": 0}
            )
            fc["n"] += 1
            for key, value in (
                ("city", city),
                ("state", state),
                ("zip", zip_code),
                ("address", full),
            ):
                if not fc[key] and value:
                    fc[key] = value
        return out

    def list_fc_regions(self) -> list[FcRegionOut]:
        board = self._board_fcs()
        saved = {r.fc: r for r in self.session.scalars(select(WfsFcRegion))}
        items = []
        for code in sorted(set(board) | set(saved)):
            seen = board.get(code, {})
            row = saved.get(code)
            items.append(
                FcRegionOut(
                    fc=code,
                    name=row.name if row else None,
                    zip=seen.get("zip"),
                    city=seen.get("city"),
                    state=seen.get("state"),
                    address=seen.get("address"),
                    region=_region(row.region if row else region_of_state(seen.get("state"))),
                    region_source="saved" if row else "state",
                    shipments=seen.get("n", 0),
                    updated_by=row.updated_by if row else None,
                    updated_at=row.updated_at if row else None,
                )
            )
        return items

    def update_fc_region(self, fc: str, cmd: FcRegionUpdate, actor: str) -> FcRegionOut:
        row = self.session.get(WfsFcRegion, fc)
        if row is None and fc not in self._board_fcs():
            raise ApiError(code="NOT_FOUND", status_code=404, message="看板上没有这个 FC")
        before = {"region": row.region, "name": row.name} if row else None
        if row is None:
            row = WfsFcRegion(fc=fc, region=cmd.region, name=cmd.name, updated_by=actor)
            self.session.add(row)
        else:
            row.region, row.name = cmd.region, cmd.name
            row.updated_by, row.updated_at = actor, datetime.now(UTC)
        self._log(
            "fc_region", fc, before, {"region": cmd.region, "name": cmd.name}, cmd.reason, actor
        )
        self.session.commit()
        return next(i for i in self.list_fc_regions() if i.fc == fc)

    # ---- creation defaults ----------------------------------------------------------

    def _account(self, account: str | None) -> str:
        if account is None:
            # The page does not know account refs; one account in scope is unambiguous.
            if len(self.accounts) != 1:
                raise ApiError(
                    code="WFS_SETTINGS_ACCOUNT_REQUIRED",
                    status_code=422,
                    message="请指定来源账号",
                )
            return next(iter(self.accounts))
        if account not in self.accounts:
            raise ApiError(code="DATA_SCOPE_DENIED", status_code=403)
        return account

    def get_creation_defaults(self, account: str | None) -> CreationDefaultsOut:
        account = self._account(account)
        row = self.session.get(WfsCreationDefaults, account)
        if row is None:
            return CreationDefaultsOut(source_account_ref=account, saved=False, **CREATION_DEFAULTS)
        return CreationDefaultsOut(
            source_account_ref=account,
            saved=True,
            transport=row.transport,
            ship_date_offset=row.ship_date_offset,
            pallet_boxes=row.pallet_boxes,
            mixed_boxes=row.mixed_boxes,
            carrier_opt=row.carrier_opt,
            updated_by=row.updated_by,
            updated_at=row.updated_at,
        )

    def update_creation_defaults(
        self, cmd: CreationDefaultsUpdate, actor: str
    ) -> CreationDefaultsOut:
        account = self._account(cmd.source_account_ref)
        before = self.get_creation_defaults(account)
        values = cmd.model_dump(exclude={"source_account_ref", "reason"})
        row = self.session.get(WfsCreationDefaults, account)
        if row is None:
            self.session.add(
                WfsCreationDefaults(source_account_ref=account, updated_by=actor, **values)
            )
        else:
            for key, value in values.items():
                setattr(row, key, value)
            row.updated_by, row.updated_at = actor, datetime.now(UTC)
        before_values = before.model_dump(include=set(values)) if before.saved else None
        self._log("creation_defaults", account, before_values, values, cmd.reason, actor)
        self.session.commit()
        return self.get_creation_defaults(account)

    # ---- read-only dictionary / log -------------------------------------------------

    def logistics_channels(self) -> tuple[list[LogisticsChannelOut], bool]:
        current = select(PmcWfsSourceFile.id).where(
            PmcWfsSourceFile.source == "lingxing",
            PmcWfsSourceFile.endpoint == "logistics_channels",
            PmcWfsSourceFile.is_current.is_(True),
        )
        rows = list(
            self.session.scalars(
                select(LingxingLogisticsChannelOds)
                .where(LingxingLogisticsChannelOds.file_id.in_(current))
                .order_by(
                    LingxingLogisticsChannelOds.provider_name,
                    LingxingLogisticsChannelOds.channel_id,
                )
            )
        )
        items = [
            LogisticsChannelOut(
                provider_id=r.provider_id,
                provider_name=r.provider_name,
                channel_id=r.channel_id,
                channel_name=r.channel_name,
                method_name=r.method_name,
                enabled=(r.enabled or "").strip() in ("1", "true", "True", "启用"),
            )
            for r in rows
        ]
        return items, bool(items)

    def list_changes(self, query: ChangeQuery) -> tuple[list[SettingsChangeOut], int]:
        stmt = select(WfsSettingsChange)
        if query.entity:
            stmt = stmt.where(WfsSettingsChange.entity == query.entity)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(
            stmt.order_by(WfsSettingsChange.created_at.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        return [
            SettingsChangeOut(
                entity=r.entity,
                entity_key=r.entity_key,
                before=r.before_json,
                after=r.after_json,
                reason=r.reason,
                actor=r.actor,
                created_at=r.created_at,
            )
            for r in rows
        ], total

    def _log(self, entity: str, key: str, before: Any, after: Any, reason: str, actor: str) -> None:
        self.session.add(
            WfsSettingsChange(
                entity=entity,
                entity_key=key,
                before_json=before,
                after_json=after,
                reason=reason,
                actor=actor,
            )
        )
