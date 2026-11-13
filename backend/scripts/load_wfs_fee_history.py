#!/usr/bin/env python3
"""把历史 WFS 费用数据导入新系统（上线后由部署 AI 按票据在服务器上执行；数据不进仓库）。

三种输入，都走和页面导入同一条路（WfsFeeService.upload，origin=history）：
1. 结算报表原始 CSV（沃尔玛接口下载的 SettlementReport_*.csv，或卖家后台下载的）：
   --settlement <目录>，目录结构 <store_code 或 store_id>/**/*.csv；
   店铺由 Partner ID 映射或目录名决定。
2. 旧系统仓储费（fact_wfs_storage_fee.csv 只读导出）：按 店铺 × 账期 合成一份带汇总块的
   仓储报表再导入；只取 14 天标准账期（跨月 / 自定义区间的行是核验用的，不入）。
3. 旧系统入库运费分摊（fact_inbound_freight_alloc.csv 只读导出）：按 店铺 × 账期 合成入库报告导入，
   再把旧系统分到各 msku 的金额写成分摊子行（basis=旧系统分摊），不重新按货件算。

用法（服务器上，激活后端 .venv，连生产库需 Rocky 授权）：
  python scripts/load_wfs_fee_history.py --stores '{"<店铺代码>":"<店铺 id>", ...}' \
      --settlement /srv/wfs_history/settlement --storage /srv/wfs_history/fact_wfs_storage_fee.csv \
      --inbound /srv/wfs_history/fact_inbound_freight_alloc.csv [--dry-run]
不打印任何凭证；每个文件只回报 店铺 / 类型 / 账期 / 新增 / 重复 / 拒收原因。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.modules.wfs_fees import attribution as rules  # noqa: E402
from app.modules.wfs_fees.models import WalmartWfsFeeLine  # noqa: E402
from app.modules.wfs_fees.parsing import ParseError, expand_upload  # noqa: E402
from app.modules.wfs_fees.service import WfsFeeService  # noqa: E402

ACTOR = "history-load"


def _csv(rows: list[list[str]]) -> bytes:
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return out.getvalue().encode("utf-8")


def _report(result) -> None:
    print(
        f"{result.store_id} {result.fee_source} {result.period_start}~{result.period_end} "
        f"{result.status} rows={result.rows_parsed} new={result.rows_new} "
        f"dup={result.rows_duplicate} {result.reject_reason or ''} {' | '.join(result.warnings)}"
    )


def load_settlement(
    service: WfsFeeService, root: Path, stores: dict[str, str], dry_run: bool
) -> None:
    paths = sorted(p for p in root.rglob("*") if p.suffix.lower() in {".csv", ".zip"})
    for path in paths:
        if "_original" in path.relative_to(root).parts[:-1]:
            continue  # 原件备份目录，和已转换的 CSV 重复
        top = path.relative_to(root).parts[0]
        store_id = stores.get(top, top if top.isdecimal() else None)
        if dry_run:
            print(f"[dry-run] settlement {store_id or '?'} {path.name}")
            continue
        try:
            parts = expand_upload(path.name, path.read_bytes())
        except ParseError as exc:
            print(f"{store_id or '?'} {path.name} 跳过：{exc}")
            continue
        for name, content in parts:
            _report(
                service.upload(
                    file_name=name,
                    content=content,
                    actor=ACTOR,
                    request_id=None,
                    store_id=store_id,
                    origin="history",
                )
            )


STORAGE_HEAD = [
    "GTIN",
    "SKU",
    "Item ID",
    "Item Name",
    "Days in report period",
    "Final storage fee",
    "Original Amount",
    "Discount Savings",
    "Standard: average daily units available",
    "Long-term (366-450 days): average daily units available",
    "Long-term (450+ days): average daily units available",
]


def load_storage(service: WfsFeeService, path: Path, dry_run: bool) -> None:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in csv.DictReader(open(path, encoding="utf-8-sig")):
        start, end = row["report_start"][:10], row["report_end"][:10]
        if (date.fromisoformat(end) - date.fromisoformat(start)).days + 1 != 14:
            continue  # 跨月 / 自定义区间只做核验，不入
        groups[(row["store_id"], start, end)].append(row)
    for (store_id, start, end), rows in sorted(groups.items()):
        body = [
            [
                r["gtin"],
                r["sku"],
                r.get("item_id") or "",
                "",
                r.get("days_in_period") or "14",
                r["final_storage_fee"],
                r.get("original_amount") or r["final_storage_fee"],
                r.get("discount_savings") or "0",
                r.get("avg_units_standard") or "0",
                r.get("avg_units_longterm") or "0",
                "0",
            ]
            for r in rows
        ]
        total = sum(Decimal(r["final_storage_fee"] or 0) for r in rows)
        content = _csv(
            [
                ["STORE"],
                ["Report start date", "Report end date", "Total storage fees"],
                [start, end, f"{total:.2f}"],
                STORAGE_HEAD,
                *body,
            ]
        )
        if dry_run:
            print(f"[dry-run] storage {store_id} {start}~{end} rows={len(rows)} total={total:.2f}")
            continue
        _report(
            service.upload(
                file_name=f"oldsys_storage_{store_id}_{start}_{end}.csv",
                content=content,
                actor=ACTOR,
                request_id=None,
                store_id=store_id,
                origin="history",
            )
        )


INBOUND_HEAD = ["Shipment ID", "Delivery Date", "Service Type", "Reason Code", "Actual Charge"]


def load_inbound(service: WfsFeeService, path: Path, dry_run: bool) -> None:
    groups: dict[tuple[str, str, str], dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in csv.DictReader(open(path, encoding="utf-8-sig")):
        groups[(row["store_id"], row["report_start"][:10], row["report_end"][:10])][
            row["cargo_code"].strip().upper()
        ].append(row)
    for (store_id, start, end), cargos in sorted(groups.items()):
        body = [
            [cargo, end, "旧系统", "", f"{Decimal(rows[0]['freight_total'] or 0):.2f}"]
            for cargo, rows in cargos.items()
            if cargo
        ]
        content = _csv(
            [
                ["STORE"],
                ["ReportingPeriod_StartDate", "ReportingPeriod_EndDate"],
                [start, end],
                INBOUND_HEAD,
                *body,
            ]
        )
        if dry_run:
            print(f"[dry-run] inbound {store_id} {start}~{end} cargos={len(body)}")
            continue
        result = service.upload(
            file_name=f"oldsys_inbound_{store_id}_{start}_{end}.csv",
            content=content,
            actor=ACTOR,
            request_id=None,
            store_id=store_id,
            origin="history",
        )
        _report(result)
        if result.status != "parsed":
            continue
        # 旧系统已经分到 msku 的，照旧系统的比例写子行（alloc_basis=none 的整额留着未分摊）
        session = service.session
        listings = service._listings({store_id})
        for cargo, rows in cargos.items():
            parent = session.scalars(
                select(WalmartWfsFeeLine).where(
                    WalmartWfsFeeLine.store_id == store_id,
                    WalmartWfsFeeLine.fee_type == "InboundTransportationFee",
                    WalmartWfsFeeLine.po_number == cargo,
                    WalmartWfsFeeLine.period_start == date.fromisoformat(start),
                    WalmartWfsFeeLine.parent_line_id.is_(None),
                )
            ).first()
            allocated = [
                r
                for r in rows
                if (r.get("msku") or "").strip() and r.get("alloc_basis") not in ("", "none")
            ]
            if parent is None or not allocated:
                continue
            service._drop_children(parent)
            for r in allocated:
                hit = next(
                    (
                        lst
                        for (sid, _), lst in listings.items()
                        if sid == store_id and lst.msku == r["msku"].strip()
                    ),
                    None,
                )
                share = rules.Share(
                    gtin="",
                    item_id=(r.get("item_id") or (hit.item_id if hit else "")),
                    msku=r["msku"].strip(),
                    local_sku=(hit.local_sku if hit else ""),
                    basis=f"旧系统按{r.get('alloc_basis')}分摊",
                )
                session.add(service._child(parent, share, -Decimal(r["alloc_amount"] or 0)))
            parent.attribution = rules.ATTR_ALLOCATED
            parent.allocation_basis = f"旧系统分摊到 {len(allocated)} 个 SKU"
        session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--stores", required=True, help='店铺代码 → 店铺 id 的 JSON，如 {"CN2501":"110..."}'
    )
    parser.add_argument("--settlement", type=Path)
    parser.add_argument("--storage", type=Path)
    parser.add_argument("--inbound", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stores = json.loads(args.stores)
    with get_session_factory()() as session:
        service = WfsFeeService(session, get_settings())
        if args.storage:
            load_storage(service, args.storage, args.dry_run)
        if args.inbound:
            load_inbound(service, args.inbound, args.dry_run)
        if args.settlement:
            load_settlement(service, args.settlement, stores, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
