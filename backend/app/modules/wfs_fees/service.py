"""WFS 费用明细：导入 / 归属 / 核对 / 调整 / 读取。

- 导入：原文件先存档（RAW-first，复用资金流水的 store_original），再解析、
  按 店铺 + line_key 幂等入库。同一份文件再传：只刷新，不新增。
  仓储 / 入库同账期重传 = 覆盖；账期交叉但起止不同 = 拒收（旧系统教训：CN2601 曾因此重复累加）。
  空报告也留一条 0 行的文件记录，区分「导过为空」和「没导」。
- 归期：结算报表每笔按扣费周五找领星同店同类同日账单行 → 同店同日任一账单 → 账单期起止包含；
  按天出账的退货类按交易日。仓储 / 入库按账期止日。
- 归属：attribution.py 的规则；分摊子行 parent_line_id 指向原行。
- 核对：店铺 × 账单期 × 费用类型，领星 vs 本表，结果存 mart_walmart_wfs_fee_checks。
- 调整：另存一张表，不改原行的报表字段；归属和子行按调整结果重写。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.data_pages.models import LingxingStoreDimension, WalmartListingDimension
from app.modules.finance_cashflow.service import store_original
from app.modules.walmart_bills.models import WalmartBillLine, WalmartBillPeriod
from app.modules.walmart_bills.payout_service import store_code
from app.modules.wfs_fees import attribution as rules
from app.modules.wfs_fees.models import (
    WalmartWfsFeeAdjustment,
    WalmartWfsFeeCheck,
    WalmartWfsFeeFile,
    WalmartWfsFeeLine,
)
from app.modules.wfs_fees.parsing import (
    FEE_SOURCE_INBOUND,
    FEE_SOURCE_SETTLEMENT,
    FEE_SOURCE_STORAGE,
    FULFILLMENT_FEE,
    INBOUND_FEE,
    RETURN_PROCESSING_FEE,
    STORAGE_FEE,
    ParsedLine,
    ParsedReport,
    ParseError,
    friday_of,
    parse,
)

SOURCE_REF: Final = "primary"
INBOUND_STORE_HINT: Final = "（入库运输报告没有商品，要等领星货件同步后才能自动认店）"
# 领星账单里的描述 → 本表 fee_type（领星把退货两类写成带空格的英文名）
LX_FEE_NAMES: Final = {
    "Returned Item Disposal Fee": "RC_InventoryDisposalFee",
    "Return Processing Fee": RETURN_PROCESSING_FEE,
}
# 领星按天出账（带订单号）的类型：按交易日归期；其余按扣费周五
DAILY_TYPES: Final = frozenset({"RC_InventoryDisposalFee", RETURN_PROCESSING_FEE})
CHECK_TOLERANCE: Final = Decimal("0.015")
PARTNER_MAP_SETTING: Final = "finance_wfs_partner_store_map"


class WfsFeeError(Exception):
    """给接口用的业务错误：code 稳定、message 给财务看。"""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class StorageNotConfiguredError(WfsFeeError):
    def __init__(self) -> None:
        super().__init__("WFS_FEE_STORAGE_NOT_CONFIGURED", "原件存储目录没有配置", 503)


@dataclass
class ImportResult:
    file_id: UUID
    file_name: str
    store_id: str
    fee_source: str
    period_start: date | None
    period_end: date | None
    status: str
    rows_parsed: int
    rows_new: int
    rows_duplicate: int
    duplicate_of_file: bool = False
    reject_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    # 认不出店铺被拒收：页面在这一行给出店铺下拉，选了再传同一个文件
    needs_store: bool = False


def utc_now() -> datetime:
    return datetime.now(UTC)


def partner_store_map(settings: Settings) -> dict[str, str]:
    """结算报表 Partner ID → 店铺 id。

    真实值在线上 app.env（FINANCE_WFS_PARTNER_STORE_MAP，JSON），不进仓库。
    """
    raw = getattr(settings, PARTNER_MAP_SETTING, None) or ""
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


class WfsFeeService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    # ------------------------------------------------------------ 导入

    def upload(
        self,
        *,
        file_name: str,
        content: bytes,
        actor: str,
        request_id: str | None,
        store_id: str | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
        origin: str = "upload",
        sync_run_id: UUID | None = None,
    ) -> ImportResult:
        root = self.settings.media_storage_root
        if root is None:
            raise StorageNotConfiguredError
        sha256 = hashlib.sha256(content).hexdigest()
        try:
            report = parse(content, period_start=period_start, period_end=period_end)
        except ParseError as exc:
            return self._reject(
                file_name,
                sha256,
                content,
                root,
                store_id or "",
                "settlement",
                str(exc),
                actor,
                request_id,
                origin,
            )
        # 同一份文件不分店先查：导过的文件再传，店铺跟着以前那次走（复审 P2-3）
        earlier = self._duplicate_file(sha256)
        resolved, why = self._resolve_store(report, store_id, file_name)
        if resolved is None and earlier is not None and not why:
            resolved = earlier.store_id
        if resolved is None:
            result = self._reject(
                file_name,
                sha256,
                content,
                root,
                "",
                report.fee_source,
                why
                or (
                    "认不出是哪家店：文件里的商品对不上唯一一家店铺"
                    + (INBOUND_STORE_HINT if report.fee_source == FEE_SOURCE_INBOUND else "")
                    + "，请在这一行选店铺后重新导入"
                ),
                actor,
                request_id,
                origin,
            )
            result.needs_store = True
            return result
        if earlier is not None and earlier.store_id != resolved:
            return self._reject(
                file_name,
                sha256,
                content,
                root,
                resolved,
                report.fee_source,
                f"此文件已导入到 {self._store_label(earlier.store_id)} 店，不能再导入到 "
                f"{self._store_label(resolved)} 店；如果之前导错了，请联系管理员处理",
                actor,
                request_id,
                origin,
            )
        duplicate = earlier
        if duplicate is not None:
            # 同一份文件再传：按现在的规则重新解析刷新（归期、归属可能变了），不新增行
            result = self._ingest(duplicate, report, resolved, actor, request_id)
            result.duplicate_of_file = True
            self.session.commit()
            return result
        if report.fee_source in (FEE_SOURCE_STORAGE, FEE_SOURCE_INBOUND):
            clash = self._period_clash(resolved, report)
            if clash:
                return self._reject(
                    file_name,
                    sha256,
                    content,
                    root,
                    resolved,
                    report.fee_source,
                    clash,
                    actor,
                    request_id,
                    origin,
                )
        storage_path = store_original(Path(root), sha256, "csv", content)
        record = WalmartWfsFeeFile(
            source_account_ref=SOURCE_REF,
            store_id=resolved,
            fee_source=report.fee_source,
            origin=origin,
            file_name=file_name[:255],
            sha256=sha256,
            storage_path=storage_path,
            period_start=report.period_start,
            period_end=report.period_end,
            declared_total=report.declared_total,
            status="parsed" if report.lines else "empty",
            sync_run_id=sync_run_id,
            actor=actor,
            request_id=request_id,
        )
        self.session.add(record)
        self.session.flush()
        result = self._ingest(record, report, resolved, actor, request_id)
        self.session.commit()
        return result

    def _reject(
        self,
        file_name,
        sha256,
        content,
        root,
        store_id,
        fee_source,
        reason,
        actor,
        request_id,
        origin,
    ) -> ImportResult:
        storage_path = store_original(Path(root), sha256, "csv", content)
        record = WalmartWfsFeeFile(
            source_account_ref=SOURCE_REF,
            store_id=store_id or "0",
            fee_source=fee_source,
            origin=origin,
            file_name=file_name[:255],
            sha256=sha256,
            storage_path=storage_path,
            status="rejected",
            reject_reason=reason[:2000],
            actor=actor,
            request_id=request_id,
        )
        self.session.add(record)
        self.session.commit()
        return ImportResult(
            record.id,
            file_name,
            store_id or "",
            fee_source,
            None,
            None,
            "rejected",
            0,
            0,
            0,
            reject_reason=reason,
        )

    def _resolve_store(
        self, report: ParsedReport, store_id: str | None, file_name: str = ""
    ) -> tuple[str | None, str]:
        """认店铺，不用人选（Rocky 11-13）。返回 (店铺, 拒收原因)。

        1. 结算报表的 Partner ID：配置表 → 以前导入过同一 Partner ID 的店铺（唯一才算）；
        2. 文件里的商品（SKU / GTIN / Item ID）对商品表投票：只有一家店覆盖 ≥ 80% 的可匹配行、
           且可匹配行 ≥ 有商品信息行的 50% 才算；多店共有的商品分不出来 → 认不出；
        3. 学到的 Partner 店铺和投票唯一认出的店不一致 → 拒收（让人核对），页面选了其中一家才放行；
        4. 文件里没有任何费用行（空报告 / 只有汇总行）时，才看卖家后台文件名里的 Partner ID，
           且必须是以前从文件内容里学到过的；
        5. 认不出时才用页面上选的店铺（只补空，不覆盖自动认出的店）。
        """
        picked = store_id if store_id and store_id.isdecimal() else None
        partner, learned = (
            self._partner_store(report.partner_id) if report.partner_id else (None, False)
        )
        voted = self._vote_store(report)
        if partner and voted and partner != voted:
            if learned:
                if picked in (partner, voted):
                    return picked, ""
                return None, (
                    f"店铺对不上：文件的 Partner ID 以前导入在 {self._store_label(partner)} 店，"
                    f"但文件里的商品属于 {self._store_label(voted)} 店，"
                    "请核对后在这一行选店铺重新导入"
                )
            return partner, ""  # 配置表里登记的 Partner ID 为准
        known = partner or voted
        if not known and not report.lines:
            known = self._file_name_store(file_name)
        if known:
            return known, ""
        return picked, ""

    def _store_label(self, store_id: str) -> str:
        name = self.session.scalar(
            select(LingxingStoreDimension.store_name)
            .where(
                LingxingStoreDimension.store_id == store_id,
                LingxingStoreDimension.platform_code == "walmart",
            )
            .limit(1)
        )
        return store_code(name, store_id)

    def _partner_store(self, partner_id: str) -> tuple[str | None, bool]:
        """(店铺, 是否从以前导入学到的)；配置表登记的为 (店铺, False)。"""
        mapped = partner_store_map(self.settings).get(partner_id)
        if mapped:
            return mapped, False
        seen = self.session.scalars(
            select(WalmartWfsFeeLine.store_id)
            .where(
                WalmartWfsFeeLine.source_account_ref == SOURCE_REF,
                WalmartWfsFeeLine.partner_id == partner_id[:32],
            )
            .distinct()
            .limit(2)
        ).all()
        return (seen[0], True) if len(seen) == 1 else (None, False)

    def _file_name_store(self, file_name: str) -> str | None:
        """文件名里的长数字串当 Partner ID 去对；只认以前从文件内容里学到的，对不上就不认。"""
        stores = {
            store
            for digits in re.findall(r"(?<!\d)\d{8,20}(?!\d)", file_name)
            if (store := self._partner_store(digits)[0])
        }
        return stores.pop() if len(stores) == 1 else None

    def _vote_store(self, report: ParsedReport) -> str | None:
        skus = {line.sku.strip() for line in report.lines if line.sku.strip()}
        gtins = {line.gtin.strip().lstrip("0") for line in report.lines if line.gtin.strip()}
        items = {line.item_id.strip() for line in report.lines if line.item_id.strip()}
        if not (skus or gtins or items):
            return None
        conditions = []
        if skus:
            conditions.append(WalmartListingDimension.msku.in_(skus))
        if items:
            conditions.append(WalmartListingDimension.item_id.in_(items))
        if gtins:
            padded = {g.zfill(14) for g in gtins} | {g.zfill(12) for g in gtins} | gtins
            conditions.append(WalmartListingDimension.gtin.in_(padded))
            conditions.append(WalmartListingDimension.upc.in_(padded))
        by_sku: dict[str, set[str]] = defaultdict(set)
        by_gtin: dict[str, set[str]] = defaultdict(set)
        by_item: dict[str, set[str]] = defaultdict(set)
        for row in self.session.execute(
            select(
                WalmartListingDimension.store_id,
                WalmartListingDimension.msku,
                WalmartListingDimension.gtin,
                WalmartListingDimension.upc,
                WalmartListingDimension.item_id,
            ).where(WalmartListingDimension.source_account_ref == SOURCE_REF, or_(*conditions))
        ):
            if row.msku:
                by_sku[row.msku.strip()].add(row.store_id)
            for code in (row.gtin, row.upc):
                if code and code.strip():
                    by_gtin[code.strip().lstrip("0")].add(row.store_id)
            if row.item_id:
                by_item[row.item_id.strip()].add(row.store_id)
        votes: dict[str, int] = defaultdict(int)
        matched = 0
        informative = sum(
            1
            for line in report.lines
            if line.sku.strip() or line.gtin.strip() or line.item_id.strip()
        )
        for line in report.lines:
            # SKU 是店铺自己的编码，最准；没有 SKU 再看 GTIN、Item ID
            stores = (
                by_sku.get(line.sku.strip())
                or by_gtin.get(line.gtin.strip().lstrip("0"))
                or by_item.get(line.item_id.strip())
            )
            if not stores:
                continue
            matched += 1
            for store in stores:
                votes[store] += 1
        # 覆盖太少（大部分商品对不上）不认；只有一家店覆盖 ≥ 80% 才认（复审 P1-1）
        if not votes or matched < 0.5 * informative:
            return None
        strong = [store for store, count in votes.items() if count >= 0.8 * matched]
        return strong[0] if len(strong) == 1 else None

    def _duplicate_file(self, sha256: str) -> WalmartWfsFeeFile | None:
        """同一份文件（按内容，不分店）以前导入过的那条记录。"""
        return self.session.scalars(
            select(WalmartWfsFeeFile)
            .where(
                WalmartWfsFeeFile.source_account_ref == SOURCE_REF,
                WalmartWfsFeeFile.sha256 == sha256,
                WalmartWfsFeeFile.status != "rejected",
            )
            .order_by(WalmartWfsFeeFile.created_at.desc())
            .limit(1)
        ).first()

    def _period_clash(self, store_id: str, report: ParsedReport) -> str | None:
        """同账期重导 = 覆盖；和已有账期时间相交但起止不同 = 拒收。"""
        rows = self.session.execute(
            select(WalmartWfsFeeFile.period_start, WalmartWfsFeeFile.period_end, func.count())
            .where(
                WalmartWfsFeeFile.store_id == store_id,
                WalmartWfsFeeFile.fee_source == report.fee_source,
                WalmartWfsFeeFile.status != "rejected",
                WalmartWfsFeeFile.period_start <= report.period_end,
                WalmartWfsFeeFile.period_end >= report.period_start,
            )
            .group_by(WalmartWfsFeeFile.period_start, WalmartWfsFeeFile.period_end)
        ).all()
        clashes = [
            f"{s}~{e}" for s, e, _ in rows if (s, e) != (report.period_start, report.period_end)
        ]
        if clashes:
            return (
                f"账期重叠，已拒收：本次 {report.period_start} ~ {report.period_end} 与已导入的 "
                f"{'、'.join(clashes)} 时间相交，同时入库会重复累加。"
                "请用和已有账期一致的标准账期报表"
            )
        return None

    def _ingest(
        self,
        record: WalmartWfsFeeFile,
        report: ParsedReport,
        store_id: str,
        actor: str,
        request_id: str | None,
    ) -> ImportResult:
        now = utc_now()
        keys = [line.line_key for line in report.lines]
        existing = (
            {
                row.line_key: row
                for row in self.session.scalars(
                    select(WalmartWfsFeeLine).where(
                        WalmartWfsFeeLine.store_id == store_id, WalmartWfsFeeLine.line_key.in_(keys)
                    )
                )
            }
            if keys
            else {}
        )
        bills = _BillIndex(self.session, store_id)
        new_rows = 0
        touched: list[WalmartWfsFeeLine] = []
        amount_changed: set[UUID] = set()
        for parsed in report.lines:
            row = existing.get(parsed.line_key)
            if row is None:
                row = WalmartWfsFeeLine(
                    source_account_ref=SOURCE_REF,
                    store_id=store_id,
                    fee_source=report.fee_source,
                    line_key=parsed.line_key,
                    raw_file_id=record.id,
                    last_file_id=record.id,
                    attribution=rules.ATTR_UNALLOCATED,
                    amount_usd=parsed.amount_usd,
                    transaction_date=parsed.transaction_date,
                    date_charged=parsed.transaction_date,
                )
                self.session.add(row)
                new_rows += 1
                before = None
            else:
                before = row.amount_usd
            self._fill(row, parsed, report, bills)
            if before is not None and before != row.amount_usd:
                amount_changed.add(row.id)
            row.last_file_id = record.id
            row.missing_since = None
            row.updated_at = now
            touched.append(row)
        # 仓储 / 入库同账期重传：上次有、这次没有的行标 missing
        if report.fee_source in (FEE_SOURCE_STORAGE, FEE_SOURCE_INBOUND) and report.period_start:
            for row in self.session.scalars(
                select(WalmartWfsFeeLine).where(
                    WalmartWfsFeeLine.store_id == store_id,
                    WalmartWfsFeeLine.fee_source == report.fee_source,
                    WalmartWfsFeeLine.period_start == report.period_start,
                    WalmartWfsFeeLine.period_end == report.period_end,
                    WalmartWfsFeeLine.parent_line_id.is_(None),
                    WalmartWfsFeeLine.missing_since.is_(None),
                )
            ):
                if row.line_key not in {line.line_key for line in report.lines}:
                    row.missing_since = now
        self.session.flush()
        self.attribute(touched, amount_changed=amount_changed)
        record.row_count = len(report.lines)
        record.rows_new = new_rows
        record.rows_duplicate = len(report.lines) - new_rows
        record.status = "parsed" if report.lines else "empty"
        self.refresh_checks(store_id, {row.report_key for row in touched if row.report_key})
        return ImportResult(
            record.id,
            record.file_name,
            store_id,
            report.fee_source,
            report.period_start,
            report.period_end,
            record.status,
            len(report.lines),
            new_rows,
            len(report.lines) - new_rows,
            warnings=list(report.warnings),
        )

    def _fill(
        self, row: WalmartWfsFeeLine, parsed: ParsedLine, report: ParsedReport, bills: _BillIndex
    ) -> None:
        row.fee_type = parsed.fee_type
        row.reason_code = parsed.reason_code[:128]
        row.detail = parsed.detail
        row.source_ref = parsed.source_ref[:255]
        row.transaction_date = parsed.transaction_date
        row.po_number = parsed.po_number
        row.partner_id = parsed.partner_id[:32]
        row.gtin = parsed.gtin[:32]
        row.quantity = parsed.quantity
        row.amount_usd = parsed.amount_usd
        row.original_amount = parsed.original_amount
        row.discount_savings = parsed.discount_savings
        row.extra = dict(parsed.extra)
        if parsed.item_id and not row.item_id:
            row.item_id = parsed.item_id
        if parsed.sku and not row.msku:
            row.msku = parsed.sku
        if report.fee_source == FEE_SOURCE_SETTLEMENT:
            row.date_charged = (
                parsed.transaction_date
                if parsed.fee_type in DAILY_TYPES
                else friday_of(parsed.transaction_date)
            )
            row.period_start = row.period_end = None
        else:
            row.period_start, row.period_end = report.period_start, report.period_end
            row.date_charged = report.period_end or parsed.transaction_date
        row.report_key, row.report_date, row.bill_match = bills.locate(
            row.fee_type, row.date_charged, row.period_start, row.period_end
        )

    # ------------------------------------------------------------ 归属

    def attribute(
        self, rows: list[WalmartWfsFeeLine], *, amount_changed: set[UUID] | None = None
    ) -> None:
        """对这些原行重算归属和分摊子行（已人工调整过的不动）。

        人工调整过的行重导后原金额变了：人工分摊的合计已经不等于原行，标「待核」让财务重做，
        不自动改人工的分法（复审 P2-6）。
        """
        if not rows:
            return
        adjusted = self._adjusted_ids([row.id for row in rows])
        store_ids = {row.store_id for row in rows}
        listings = self._listings(store_ids)
        for row in rows:
            if row.parent_line_id is not None:
                continue
            if row.id in adjusted:
                # 记公司的不受金额影响；人工分到商品的才需要重做
                if (
                    amount_changed
                    and row.id in amount_changed
                    and row.attribution != rules.ATTR_COMPANY
                ):
                    row.attribution = rules.ATTR_ALLOCATED_CHECK
                    row.allocation_basis = "原金额已变，人工分摊需重做"
                continue
            self._drop_children(row)
            if row.gtin:
                hit = rules.lookup(listings, row.store_id, row.gtin)
                if hit:
                    row.item_id, row.msku, row.local_sku = hit.item_id, hit.msku, hit.local_sku
                    row.attribution = rules.ATTR_MATCHED
                    row.allocation_basis = ""
                else:
                    row.attribution = rules.ATTR_UNMATCHED
                    row.allocation_basis = "店铺 + GTIN 在商品表里没有"
                continue
            if row.fee_type == INBOUND_FEE:
                result = rules.allocate_inbound(
                    row.amount_usd, self._shipment_items(row.store_id, row.po_number, listings)
                )
            else:
                result = rules.allocate_no_gtin(
                    fee_type=row.fee_type,
                    reason_code=row.reason_code,
                    detail=row.detail,
                    amount=row.amount_usd,
                    cargo_shares=self._cargo_shares(
                        row.store_id, rules.cargo_in_detail(row.detail)
                    ),
                    storage_base=self._storage_base(row, listings),
                    fulfillment_base=self._fulfillment_base(row),
                    listings=listings,
                    store_id=row.store_id,
                )
            row.attribution = result.attribution
            row.allocation_basis = result.note[:2000]
            for share, amount in result.children:
                self.session.add(self._child(row, share, amount))
        self.session.flush()

    def _child(
        self, row: WalmartWfsFeeLine, share: rules.Share, amount: Decimal
    ) -> WalmartWfsFeeLine:
        key = hashlib.sha256(
            f"{row.line_key}|child|{share.gtin}|{share.msku}|{share.item_id}".encode()
        ).hexdigest()[:64]
        return WalmartWfsFeeLine(
            source_account_ref=row.source_account_ref,
            store_id=row.store_id,
            fee_source=row.fee_source,
            fee_type=row.fee_type,
            reason_code=row.reason_code,
            detail=row.detail,
            line_key=key,
            source_ref=row.source_ref,
            transaction_date=row.transaction_date,
            date_charged=row.date_charged,
            period_start=row.period_start,
            period_end=row.period_end,
            report_key=row.report_key,
            report_date=row.report_date,
            bill_match=row.bill_match,
            po_number=row.po_number,
            partner_id=row.partner_id,
            gtin=share.gtin,
            item_id=share.item_id,
            msku=share.msku,
            local_sku=share.local_sku,
            amount_usd=amount,
            attribution=rules.ATTR_ALLOCATED,
            allocation_basis=share.basis[:2000],
            parent_line_id=row.id,
            raw_file_id=row.raw_file_id,
            last_file_id=row.last_file_id,
        )

    def _drop_children(self, row: WalmartWfsFeeLine) -> None:
        self.session.execute(
            delete(WalmartWfsFeeLine).where(WalmartWfsFeeLine.parent_line_id == row.id)
        )

    def _adjusted_ids(self, ids: list[UUID]) -> set[UUID]:
        return set(
            self.session.scalars(
                select(WalmartWfsFeeAdjustment.line_id).where(
                    WalmartWfsFeeAdjustment.line_id.in_(ids),
                    WalmartWfsFeeAdjustment.kind.in_(("realloc", "company")),
                )
            )
        )

    def _listings(self, store_ids: set[str]) -> dict[tuple[str, str], rules.Listing]:
        out: dict[tuple[str, str], rules.Listing] = {}
        for row in self.session.scalars(
            select(WalmartListingDimension).where(WalmartListingDimension.store_id.in_(store_ids))
        ):
            for gtin in {(row.gtin or "").strip(), (row.upc or "").strip()}:
                if gtin:
                    out.setdefault(
                        (row.store_id, gtin.zfill(14)),
                        rules.Listing(row.item_id or "", row.msku or "", row.local_sku or ""),
                    )
                    out.setdefault(
                        (row.store_id, gtin),
                        rules.Listing(row.item_id or "", row.msku or "", row.local_sku or ""),
                    )
        return out

    def _cargo_shares(self, store_id: str, cargo: str) -> dict[str, list[rules.Share]]:
        """货件的入库运费分摊子行 → 各商品比例（按分到的金额）。"""
        if not cargo:
            return {}
        parent = self.session.scalars(
            select(WalmartWfsFeeLine)
            .where(
                WalmartWfsFeeLine.store_id == store_id,
                WalmartWfsFeeLine.fee_type == INBOUND_FEE,
                WalmartWfsFeeLine.po_number == cargo,
                WalmartWfsFeeLine.parent_line_id.is_(None),
            )
            .order_by(WalmartWfsFeeLine.period_end.desc())
            .limit(1)
        ).first()
        if parent is None:
            return {}
        children = list(
            self.session.scalars(
                select(WalmartWfsFeeLine).where(WalmartWfsFeeLine.parent_line_id == parent.id)
            )
        )
        return (
            {
                cargo: [
                    rules.Share(
                        gtin=c.gtin,
                        item_id=c.item_id,
                        msku=c.msku,
                        local_sku=c.local_sku,
                        weight=abs(c.amount_usd),
                        basis=f"货件 {cargo} 入库运费分摊比例",
                    )
                    for c in children
                ]
            }
            if children
            else {}
        )

    def _storage_base(
        self, row: WalmartWfsFeeLine, listings
    ) -> dict[tuple[str, str], tuple[Decimal, Decimal, rules.Listing | None]] | None:
        period = rules.parse_rebate_period(row.detail)
        if not period or "storage" not in (row.detail or "").lower():
            return None
        start, end = period
        base: dict[tuple[str, str], list] = {}
        for line in self.session.scalars(
            select(WalmartWfsFeeLine).where(
                WalmartWfsFeeLine.store_id == row.store_id,
                WalmartWfsFeeLine.fee_type == STORAGE_FEE,
                WalmartWfsFeeLine.parent_line_id.is_(None),
                WalmartWfsFeeLine.missing_since.is_(None),
                WalmartWfsFeeLine.period_start <= end,
                WalmartWfsFeeLine.period_end >= start,
            )
        ):
            days = (
                (line.period_end - line.period_start).days + 1
                if line.period_start and line.period_end
                else 14
            )
            overlap = (
                (min(line.period_end, end) - max(line.period_start, start)).days + 1
                if line.period_start and line.period_end
                else days
            )
            if overlap <= 0:
                continue
            orig = (
                abs(line.original_amount if line.original_amount is not None else line.amount_usd)
                * overlap
                / days
            )
            entry = base.setdefault(
                (line.gtin, line.msku),
                [Decimal("0"), Decimal("0"), rules.lookup(listings, row.store_id, line.gtin)],
            )
            entry[0] += orig
            if not line.discount_savings:
                entry[1] += orig
        return {k: (v[0], v[1], v[2]) for k, v in base.items()} or None

    def _fulfillment_base(self, row: WalmartWfsFeeLine) -> dict[str, Decimal] | None:
        """期间内无逐行折扣的配送费原价（按 GTIN）：配送费不入表，从存档的结算报表原文件里算。"""
        period = rules.parse_rebate_period(row.detail)
        if (
            not period
            or row.fee_type != "DiscountAdjustment"
            or "storage" in (row.detail or "").lower()
        ):
            return None
        start, end = period
        root = self.settings.media_storage_root
        if root is None:
            return None
        files = self.session.scalars(
            select(WalmartWfsFeeFile).where(
                WalmartWfsFeeFile.store_id == row.store_id,
                WalmartWfsFeeFile.fee_source == FEE_SOURCE_SETTLEMENT,
                WalmartWfsFeeFile.status == "parsed",
                WalmartWfsFeeFile.period_start <= end,
                WalmartWfsFeeFile.period_end >= start,
            )
        ).all()
        base: dict[str, Decimal] = defaultdict(Decimal)
        seen: set[str] = set()
        for record in files:
            path = Path(root) / record.storage_path
            if not path.is_file():
                continue
            for ref, when, gtin, orig, disc in _fulfillment_rows(path.read_bytes()):
                if not (start <= when <= end) or ref in seen:
                    continue
                seen.add(ref)
                if disc == 0:
                    base[gtin] += orig
        return dict(base) or None

    def _shipment_items(
        self, store_id: str, cargo: str, listings
    ) -> list[tuple[str, str, rules.Listing | None, Decimal, Decimal]]:
        """货件商品明细（PR 2 接领星 WFS 货件同步后填充）；PR 1 只认历史迁入的分摊子行。"""
        return []

    # ------------------------------------------------------------ 核对

    def refresh_checks(self, store_id: str, report_keys: set[str]) -> None:
        if not report_keys:
            return
        now = utc_now()
        lx: dict[tuple[str, str], list] = defaultdict(lambda: [Decimal("0"), 0, None])
        for desc, rk, rd, amount in self.session.execute(
            select(
                WalmartBillLine.transaction_description,
                WalmartBillLine.report_key,
                WalmartBillLine.report_date,
                WalmartBillLine.amount,
            ).where(
                WalmartBillLine.store_id == store_id,
                WalmartBillLine.report_key.in_(report_keys),
                WalmartBillLine.delete_flag == 0,
                WalmartBillLine.missing_since.is_(None),
                WalmartBillLine.transaction_description.like("WFS %"),
            )
        ):
            fee_type = LX_FEE_NAMES.get(desc[4:], desc[4:])
            if fee_type == FULFILLMENT_FEE:
                continue
            entry = lx[(rk, fee_type)]
            entry[0] += amount
            entry[1] += 1
            entry[2] = rd
        ours: dict[tuple[str, str], list] = defaultdict(lambda: [Decimal("0"), 0, None])
        for fee_type, rk, rd, amount in self.session.execute(
            select(
                WalmartWfsFeeLine.fee_type,
                WalmartWfsFeeLine.report_key,
                WalmartWfsFeeLine.report_date,
                WalmartWfsFeeLine.amount_usd,
            ).where(
                WalmartWfsFeeLine.store_id == store_id,
                WalmartWfsFeeLine.report_key.in_(report_keys),
                WalmartWfsFeeLine.parent_line_id.is_(None),
                WalmartWfsFeeLine.missing_since.is_(None),
            )
        ):
            entry = ours[(rk, fee_type)]
            entry[0] += amount
            entry[1] += 1
            entry[2] = rd
        existing = {
            (c.report_key, c.fee_type): c
            for c in self.session.scalars(
                select(WalmartWfsFeeCheck).where(
                    WalmartWfsFeeCheck.store_id == store_id,
                    WalmartWfsFeeCheck.report_key.in_(report_keys),
                )
            )
        }
        for key in set(lx) | set(ours):
            a, b = lx.get(key), ours.get(key)
            if a and b:
                status = "ok" if abs(a[0] - b[0]) < CHECK_TOLERANCE else "diff"
            else:
                status = "lx_only" if a else "report_only"
            check = existing.get(key) or WalmartWfsFeeCheck(
                source_account_ref=SOURCE_REF, store_id=store_id, report_key=key[0], fee_type=key[1]
            )
            if check not in existing.values():
                self.session.add(check)
            check.report_date = (a or b)[2]
            check.lingxing_amount, check.lingxing_rows = (a[0], a[1]) if a else (None, 0)
            check.report_amount, check.report_rows = (b[0], b[1]) if b else (None, 0)
            if check.status != status:
                check.verified_reason = check.verified_by = check.verified_at = None
            check.status = status
            check.refreshed_at = now
        self.session.flush()

    # ------------------------------------------------------------ 调整

    def adjust(
        self,
        line_id: UUID,
        *,
        kind: str,
        payload: dict,
        reason: str,
        actor: str,
        request_id: str | None,
    ) -> WalmartWfsFeeLine:
        row = self.session.get(WalmartWfsFeeLine, line_id)
        if row is None or row.parent_line_id is not None:
            raise WfsFeeError(
                "WFS_FEE_LINE_NOT_FOUND", "这笔费用不存在，或它是分摊子行（请调整原行）", 404
            )
        if not reason.strip():
            raise WfsFeeError("WFS_FEE_REASON_REQUIRED", "要写原因")
        if kind == "company":
            self._drop_children(row)
            row.attribution = rules.ATTR_COMPANY
            row.allocation_basis = f"人工记公司：{reason.strip()}"[:2000]
        elif kind == "realloc":
            shares = payload.get("shares") or []
            if not shares:
                raise WfsFeeError("WFS_FEE_SHARES_REQUIRED", "要给出分到哪些商品、各多少")
            listings = self._listings({row.store_id})
            total = Decimal("0")
            children = []
            for share in shares:
                amount = Decimal(str(share.get("amount") or "0")).quantize(Decimal("0.01"))
                gtin = str(share.get("gtin") or "").strip()
                hit = rules.lookup(listings, row.store_id, gtin) if gtin else None
                children.append(
                    (
                        rules.Share(
                            gtin=gtin,
                            item_id=str(share.get("item_id") or (hit.item_id if hit else "")),
                            msku=str(share.get("msku") or (hit.msku if hit else "")),
                            local_sku=(hit.local_sku if hit else ""),
                            basis=f"人工分摊：{reason.strip()}"[:500],
                        ),
                        amount,
                    )
                )
                total += amount
            if total != row.amount_usd.quantize(Decimal("0.01")):
                raise WfsFeeError(
                    "WFS_FEE_SHARES_SUM", f"分摊合计 {total} 和原行 {row.amount_usd:.2f} 不相等"
                )
            self._drop_children(row)
            for share, amount in children:
                self.session.add(self._child(row, share, amount))
            row.attribution = rules.ATTR_ALLOCATED
            row.allocation_basis = f"人工分摊到 {len(children)} 个商品：{reason.strip()}"[:2000]
        else:
            raise WfsFeeError("WFS_FEE_ADJUST_KIND", "调整类型只能是 realloc 或 company")
        self.session.add(
            WalmartWfsFeeAdjustment(
                line_id=row.id,
                kind=kind,
                payload=payload,
                reason=reason.strip(),
                actor=actor,
                request_id=request_id,
            )
        )
        row.updated_at = utc_now()
        self.session.commit()
        return row

    def verify_check(
        self, *, store_id: str, report_key: str, fee_type: str, reason: str, actor: str
    ) -> WalmartWfsFeeCheck:
        check = self.session.get(WalmartWfsFeeCheck, (SOURCE_REF, store_id, report_key, fee_type))
        if check is None:
            raise WfsFeeError("WFS_FEE_CHECK_NOT_FOUND", "没有这条核对记录", 404)
        if not reason.strip():
            raise WfsFeeError("WFS_FEE_REASON_REQUIRED", "要写原因")
        check.verified_reason, check.verified_by, check.verified_at = (
            reason.strip(),
            actor,
            utc_now(),
        )
        self.session.commit()
        return check


# ---------------------------------------------------------------- 领星账单归期


class _BillIndex:
    """一家店的领星账单：按 (类型, 日期) / (日期) / 账期起止 找 report_key。"""

    def __init__(self, session: Session, store_id: str) -> None:
        self.by_type: dict[tuple[str, date], tuple[str, date]] = {}
        self.by_day: dict[date, set[tuple[str, date]]] = defaultdict(set)
        for desc, posted, rk, rd in session.execute(
            select(
                WalmartBillLine.transaction_description,
                WalmartBillLine.posted_date,
                WalmartBillLine.report_key,
                WalmartBillLine.report_date,
            ).where(
                WalmartBillLine.store_id == store_id,
                WalmartBillLine.transaction_description.like("WFS %"),
                WalmartBillLine.delete_flag == 0,
                WalmartBillLine.missing_since.is_(None),
            )
        ):
            fee_type = LX_FEE_NAMES.get(desc[4:], desc[4:])
            self.by_type.setdefault((fee_type, posted), (rk, rd))
            self.by_day[posted].add((rk, rd))
        self.periods = [
            (p.report_key, p.report_date, p.period_start_date, p.period_end_date)
            for p in session.scalars(
                select(WalmartBillPeriod).where(
                    WalmartBillPeriod.store_id == store_id, WalmartBillPeriod.status != "voided"
                )
            )
        ]

    def locate(
        self, fee_type: str, day: date, period_start: date | None, period_end: date | None
    ) -> tuple[str | None, date | None, str]:
        hit = self.by_type.get((fee_type, day))
        if hit:
            return hit[0], hit[1], "领星同类同日"
        same_day = self.by_day.get(day) or set()
        if len(same_day) == 1:
            rk, rd = next(iter(same_day))
            return rk, rd, "领星同店同日"
        covering = [(rk, rd) for rk, rd, s, e in self.periods if s and e and s <= day <= e]
        if len(covering) == 1:
            return covering[0][0], covering[0][1], "账单期起止"
        if covering:
            rk, rd = max(covering, key=lambda x: x[1])
            return rk, rd, "账单期重叠，取较晚一期（待核）"
        return None, None, "没有对应账单"


def _fulfillment_rows(content: bytes):
    """从存档的结算报表里取配送费行：(ref, 交易日, gtin, 原价, 折扣)。给新卖家补贴分摊用。

    和导入用同一个读法（parsing._rows，newline="" 容错 \r / \r\n）；读不出来的文件、
    日期认不出的行直接跳过，不让一份坏存档把整次分摊弄失败（复审 P2-5）。
    """
    from app.modules.wfs_fees.parsing import (
        SETTLEMENT_COLUMNS,
        ParseError,
        _clean,
        _date,
        _decimal,
        _digits,
        _header_index,
        _rows,
    )

    try:
        rows = _rows(content)
    except ParseError:
        return
    head_at = next(
        (i for i, row in enumerate(rows) if _header_index(row, "Transaction Type") >= 0), -1
    )
    if head_at < 0:
        return
    header = rows[head_at]
    col = {name: _header_index(header, *names) for name, names in SETTLEMENT_COLUMNS.items()}

    def cell(row, name):
        index = col[name]
        return _clean(row[index]) if 0 <= index < len(row) else ""

    for row in rows[head_at + 1 :]:
        if cell(row, "type") != FULFILLMENT_FEE:
            continue
        try:
            when = _date(cell(row, "date"))
            orig = _decimal(cell(row, "orig")) or Decimal("0")
            disc = _decimal(cell(row, "disc")) or Decimal("0")
        except ParseError:
            continue
        if when is None:
            continue
        gtin = _digits(cell(row, "gtin"))
        ref = cell(row, "ref") or f"{when}|{gtin}|{cell(row, 'net')}"
        yield ref, when, gtin, orig, disc
