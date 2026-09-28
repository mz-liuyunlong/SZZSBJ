from __future__ import annotations

# ruff: noqa: E501
import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4
from xml.etree import ElementTree as ET

from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.modules.operation_plans.repository import OperationPlanRepository
from app.modules.operation_plans.schemas import (
    ConflictPolicy,
    OperationPlanClearanceRequest,
    OperationPlanEventListData,
    OperationPlanEventRow,
    OperationPlanImportData,
    OperationPlanImportRowResult,
    OperationPlanOptionsData,
    OperationPlanOwnerRow,
    OperationPlanProductListData,
    OperationPlanProductQuery,
    OperationPlanProductRow,
    OperationPlanSummary,
    OperationPlanSummaryData,
    OperationPlanTargetUpdateRequest,
    PeriodType,
    SelectOption,
)

PLATFORM_CODE = "walmart"
TEMPLATE_HEADERS = ["商品ID", "MSKU", "销售额（$）", "毛利润（$）", "备注"]
FAILED_HEADERS = [*TEMPLATE_HEADERS, "错误原因", "建议处理"]


@dataclass(slots=True)
class ParsedImportRow:
    row_number: int
    item_id: str
    msku: str
    sales_raw: str
    profit_raw: str
    remark: str


class OperationPlanService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OperationPlanRepository(session)

    def summary(
        self,
        *,
        period_type: PeriodType,
        period_key: str,
        account_refs: frozenset[str],
    ) -> OperationPlanSummaryData:
        period_id = self.repository.find_period_id(
            platform_code=PLATFORM_CODE,
            period_type=period_type,
            period_key=period_key,
        )
        period_progress = _period_progress(period_type, period_key)
        period_label = "本月" if period_type == "month" else "本季度"
        if period_id is None:
            return OperationPlanSummaryData(
                summary=OperationPlanSummary(
                    period_label=period_label, period_progress_rate=period_progress
                ),
                owners=[],
            )
        raw = self.repository.summary(period_id=period_id, account_refs=account_refs)
        period_elapsed_days = int(raw.get("period_elapsed_days") or 0)
        period_total_days = int(raw.get("period_total_days") or 0)
        if period_total_days > 0:
            period_progress = (
                Decimal(period_elapsed_days) / Decimal(period_total_days) * Decimal("100")
            ).quantize(Decimal("0.1"))

        summary = OperationPlanSummary(
            sales_target_amount=raw["sales_target_amount"],
            sales_actual_amount=raw["sales_actual_amount"],
            sales_forecast_amount=raw["sales_forecast_amount"],
            gross_profit_target_amount=raw["gross_profit_target_amount"],
            gross_profit_actual_amount=raw["gross_profit_actual_amount"],
            gross_profit_forecast_amount=raw["gross_profit_forecast_amount"],
            product_count=raw["product_count"],
            unplanned_count=raw["unplanned_count"],
            lagging_count=raw["lagging_count"],
            severe_lagging_count=raw["severe_lagging_count"],
            adjusted_product_count=raw["adjusted_product_count"],
            sales_target_adjust_amount=raw["sales_target_adjust_amount"],
            gross_profit_target_adjust_amount=raw["gross_profit_target_adjust_amount"],
            clearance_count=raw["clearance_count"],
            period_label=period_label,
            period_progress_rate=period_progress,
        )
        owners = [
            self._owner_row(row)
            for row in self.repository.owner_summary(period_id=period_id, account_refs=account_refs)
        ]
        return OperationPlanSummaryData(summary=summary, owners=owners)

    def list_products(
        self,
        *,
        query: OperationPlanProductQuery,
        account_refs: frozenset[str],
    ) -> OperationPlanProductListData:
        period_id = self.repository.find_period_id(
            platform_code=PLATFORM_CODE,
            period_type=query.period_type,
            period_key=query.period_key,
        )
        if period_id is None:
            return OperationPlanProductListData(
                items=[], total=0, page=query.page, page_size=query.page_size
            )
        rows, total = self.repository.list_products(
            period_id=period_id, query=query, account_refs=account_refs
        )
        items = [self._product_row(row) for row in rows]
        return OperationPlanProductListData(
            items=items, total=total, page=query.page, page_size=query.page_size
        )

    def options(
        self,
        *,
        period_type: PeriodType,
        period_key: str,
        account_refs: frozenset[str],
    ) -> OperationPlanOptionsData:
        period_id = self.repository.find_period_id(
            platform_code=PLATFORM_CODE,
            period_type=period_type,
            period_key=period_key,
        )
        owner_options: list[SelectOption] = []
        store_options: list[SelectOption] = []
        if period_id is not None:
            raw = self.repository.list_options(period_id=period_id, account_refs=account_refs)
            owner_options = [
                SelectOption(label=str(row["label"]), value=str(row["value"]))
                for row in raw["owners"]
            ]
            store_options = [
                SelectOption(label=str(row["label"]), value=str(row["value"]))
                for row in raw["stores"]
            ]
        return OperationPlanOptionsData(
            owners=owner_options,
            stores=store_options,
            operation_statuses=[
                SelectOption(label="正常运营", value="normal"),
                SelectOption(label="新品培育", value="new_product"),
                SelectOption(label="清货中", value="clearance"),
            ],
            plan_statuses=[
                SelectOption(label="正常", value="normal"),
                SelectOption(label="落后", value="lagging"),
                SelectOption(label="严重落后", value="severe_lagging"),
                SelectOption(label="未制定", value="unplanned"),
                SelectOption(label="清货", value="clearance"),
            ],
            stock_statuses=[
                SelectOption(label="库存正常", value="normal"),
                SelectOption(label="库存风险", value="risk"),
            ],
        )

    def import_file(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        period_type: PeriodType,
        period_key: str,
        conflict_policy: ConflictPolicy,
        account_refs: frozenset[str],
        actor_ref: str,
        request_id: str | None,
    ) -> OperationPlanImportData:
        start_date, end_date = _period_dates(period_type, period_key)
        period_id = self.repository.get_or_create_period(
            period_id=uuid4(),
            platform_code=PLATFORM_CODE,
            period_type=period_type,
            period_key=period_key,
            start_date=start_date,
            end_date=end_date,
            actor_ref=actor_ref,
        )
        batch_id = uuid4()
        self.repository.create_import_batch(
            batch_id=batch_id,
            period_id=period_id,
            file_name=file_name,
            file_sha256=hashlib.sha256(file_bytes).hexdigest(),
            file_size=len(file_bytes),
            conflict_policy=conflict_policy,
            actor_ref=actor_ref,
        )

        parsed_rows = parse_import_file(file_name=file_name, file_bytes=file_bytes)
        result_rows: list[OperationPlanImportRowResult] = []
        created_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        warning_count = 0
        existing_count = 0

        for parsed in parsed_rows:
            result = self._import_one_row(
                batch_id=batch_id,
                period_id=period_id,
                parsed=parsed,
                conflict_policy=conflict_policy,
                account_refs=account_refs,
                actor_ref=actor_ref,
                request_id=request_id,
            )
            result_rows.append(result)
            if result.import_status == "failed":
                failed_count += 1
            elif result.import_status == "success":
                created_count += 1
            elif result.import_status == "updated":
                updated_count += 1
                existing_count += 1
                warning_count += 1
            elif result.import_status == "skipped":
                skipped_count += 1
                existing_count += 1
                warning_count += 1

        success_count = created_count + updated_count + skipped_count
        if failed_count == 0:
            status = "completed"
        elif success_count > 0:
            status = "partial_completed"
        else:
            status = "failed"
        self.repository.update_import_batch_counts(
            batch_id=batch_id,
            status=status,
            row_count=len(result_rows),
            success_count=success_count,
            failed_count=failed_count,
            warning_count=warning_count,
            existing_count=existing_count,
            created_plan_count=created_count,
            updated_plan_count=updated_count,
            skipped_count=skipped_count,
        )
        self.session.commit()
        return OperationPlanImportData(
            batch_id=batch_id,
            status=status,
            row_count=len(result_rows),
            success_count=success_count,
            failed_count=failed_count,
            warning_count=warning_count,
            existing_count=existing_count,
            created_plan_count=created_count,
            updated_plan_count=updated_count,
            skipped_count=skipped_count,
            rows=result_rows,
        )

    def _import_one_row(
        self,
        *,
        batch_id: UUID,
        period_id: UUID,
        parsed: ParsedImportRow,
        conflict_policy: ConflictPolicy,
        account_refs: frozenset[str],
        actor_ref: str,
        request_id: str | None,
    ) -> OperationPlanImportRowResult:
        errors: list[str] = []
        item_id = parsed.item_id.strip()
        msku = parsed.msku.strip()
        if not item_id:
            errors.append("商品ID不能为空")
        if not msku:
            errors.append("MSKU不能为空")
        sales_amount, sales_error = _parse_amount(parsed.sales_raw, "销售额（$）", allow_zero=False)
        profit_amount, profit_error = _parse_amount(
            parsed.profit_raw, "毛利润（$）", allow_zero=True
        )
        if sales_error:
            errors.append(sales_error)
        if profit_error:
            errors.append(profit_error)
        if sales_amount is not None and profit_amount is not None and profit_amount > sales_amount:
            errors.append("毛利润（$）不能大于销售额（$）")

        listing: dict[str, Any] | None = None
        existing_plan: RowMapping | None = None
        plan_id: UUID | None = None
        import_status = "failed"
        error_code: str | None = None
        error_message: str | None = None
        suggestion: str | None = None

        if not errors:
            matches = self.repository.resolve_listing_by_item_msku(
                item_id=item_id,
                msku=msku,
                account_refs=account_refs,
            )
            if len(matches) == 0:
                errors.append(f"商品ID + MSKU 没有在 Listing 管理中找到：{item_id} / {msku}")
                error_code = "LISTING_NOT_FOUND"
            elif len(matches) > 1:
                errors.append(f"商品ID + MSKU 匹配到多条 Listing：{item_id} / {msku}")
                error_code = "LISTING_NOT_UNIQUE"
            else:
                listing = dict(matches[0])
                listing["source_account_ref"] = str(
                    listing.get("source_account_ref") or next(iter(account_refs))
                )
                listing["platform_code"] = str(listing.get("platform_code") or PLATFORM_CODE)
                source_account_ref = str(listing["source_account_ref"])
                platform_code = str(listing["platform_code"])
                existing_plan = self.repository.get_existing_plan(
                    period_id=period_id,
                    platform_code=platform_code,
                    source_account_ref=source_account_ref,
                    item_id=item_id,
                    msku=msku,
                )
                if existing_plan is not None and conflict_policy == "skip_existing":
                    plan_id = UUID(str(existing_plan["id"]))
                    import_status = "skipped"
                    suggestion = "该商品本周期已有计划，已按跳过已有计划处理；如需更新请重新选择覆盖已有计划导入。"
                elif existing_plan is not None:
                    plan_id = UUID(str(existing_plan["id"]))
                    self.repository.update_plan_targets(
                        plan_id=plan_id,
                        target_sales_amount=sales_amount or Decimal("0"),
                        target_gross_profit_amount=profit_amount or Decimal("0"),
                        remark=parsed.remark or None,
                        actor_ref=actor_ref,
                    )
                    self.repository.insert_event(
                        event_id=uuid4(),
                        plan_id=plan_id,
                        event_type="import_update",
                        before_data=dict(existing_plan),
                        after_data={
                            "target_sales_amount": str(sales_amount),
                            "target_gross_profit_amount": str(profit_amount),
                            "remark": parsed.remark or None,
                        },
                        reason=parsed.remark or "导入覆盖已有计划",
                        actor_ref=actor_ref,
                        request_id=request_id,
                    )
                    import_status = "updated"
                    suggestion = "已有计划已按导入文件覆盖目标金额。"
                else:
                    plan_id = uuid4()
                    self.repository.insert_plan(
                        plan_id=plan_id,
                        period_id=period_id,
                        listing=listing,
                        target_sales_amount=sales_amount or Decimal("0"),
                        target_gross_profit_amount=profit_amount or Decimal("0"),
                        remark=parsed.remark or None,
                        import_batch_id=batch_id,
                        actor_ref=actor_ref,
                    )
                    self.repository.insert_event(
                        event_id=uuid4(),
                        plan_id=plan_id,
                        event_type="import_create",
                        before_data=None,
                        after_data={
                            "item_id": item_id,
                            "msku": msku,
                            "target_sales_amount": str(sales_amount),
                            "target_gross_profit_amount": str(profit_amount),
                        },
                        reason=parsed.remark or "导入创建计划",
                        actor_ref=actor_ref,
                        request_id=request_id,
                    )
                    import_status = "success"
                    suggestion = "已成功导入。"

        if errors:
            error_message = "；".join(errors)
            suggestion = _suggestion_for_errors(errors)
            error_code = error_code or "VALIDATION_ERROR"
            import_status = "failed"

        raw = {
            "item_id": parsed.item_id,
            "msku": parsed.msku,
            "sales": parsed.sales_raw,
            "profit": parsed.profit_raw,
            "remark": parsed.remark,
        }
        self.repository.insert_import_row(
            row_id=uuid4(),
            batch_id=batch_id,
            row_number=parsed.row_number,
            raw=raw,
            target_sales_amount=sales_amount,
            target_gross_profit_amount=profit_amount,
            import_status=import_status,
            listing=listing,
            imported_plan_id=plan_id,
            error_code=error_code,
            error_message=error_message,
            suggestion=suggestion,
            validation_errors=errors,
            validation_warnings=[suggestion]
            if import_status in {"updated", "skipped"} and suggestion
            else [],
        )
        return OperationPlanImportRowResult(
            row_number=parsed.row_number,
            item_id=item_id or None,
            msku=msku or None,
            sales_target_amount=sales_amount,
            gross_profit_target_amount=profit_amount,
            remark=parsed.remark or None,
            import_status=import_status,
            error_message=error_message,
            suggestion=suggestion,
        )

    def update_targets(
        self,
        *,
        plan_id: UUID,
        payload: OperationPlanTargetUpdateRequest,
        actor_ref: str,
        request_id: str | None,
    ) -> OperationPlanProductRow:
        before = self.repository.get_plan(plan_id)
        if before is None:
            raise ValueError("商品计划不存在")
        self.repository.update_plan_targets(
            plan_id=plan_id,
            target_sales_amount=payload.sales_target_amount,
            target_gross_profit_amount=payload.gross_profit_target_amount,
            remark=payload.reason,
            actor_ref=actor_ref,
        )
        self.repository.insert_event(
            event_id=uuid4(),
            plan_id=plan_id,
            event_type="target_update",
            before_data=dict(before),
            after_data={
                "target_sales_amount": str(payload.sales_target_amount),
                "target_gross_profit_amount": str(payload.gross_profit_target_amount),
            },
            reason=payload.reason,
            actor_ref=actor_ref,
            request_id=request_id,
        )
        self.session.commit()
        row = self.repository.get_plan(plan_id)
        if row is None:
            raise ValueError("商品计划不存在")
        return self._product_row(row)

    def clearance(
        self,
        *,
        plan_id: UUID,
        payload: OperationPlanClearanceRequest,
        actor_ref: str,
        request_id: str | None,
    ) -> OperationPlanProductRow:
        before = self.repository.get_plan(plan_id)
        if before is None:
            raise ValueError("商品计划不存在")
        self.repository.mark_plan_clearance(plan_id=plan_id, actor_ref=actor_ref)
        self.repository.insert_event(
            event_id=uuid4(),
            plan_id=plan_id,
            event_type="clearance",
            before_data=dict(before),
            after_data={"operation_status": "clearance", "plan_status": "clearance"},
            reason=payload.reason,
            actor_ref=actor_ref,
            request_id=request_id,
        )
        self.session.commit()
        row = self.repository.get_plan(plan_id)
        if row is None:
            raise ValueError("商品计划不存在")
        return self._product_row(row)

    def events(self, plan_id: UUID) -> OperationPlanEventListData:
        event_labels = {
            "import_create": "导入创建",
            "import_update": "导入更新",
            "target_update": "编辑目标",
            "clearance": "转为清货",
        }
        items: list[OperationPlanEventRow] = []
        for row in self.repository.list_events(plan_id):
            after_data = row.get("after_data") or {}
            items.append(
                OperationPlanEventRow(
                    event_id=row["id"],
                    event_type=row["event_type"],
                    event_label=event_labels.get(row["event_type"], row["event_type"]),
                    sales_target_amount=_decimal_or_none(after_data.get("target_sales_amount")),
                    gross_profit_target_amount=_decimal_or_none(
                        after_data.get("target_gross_profit_amount")
                    ),
                    reason=row.get("reason"),
                    actor_name=str(row.get("actor_ref") or "系统"),
                    created_at=row["created_at"],
                )
            )
        return OperationPlanEventListData(items=items)

    def failed_export(self, batch_id: UUID) -> bytes:
        rows = []
        for row in self.repository.list_failed_import_rows(batch_id):
            rows.append(
                {
                    "商品ID": row.get("item_id_raw") or "",
                    "MSKU": row.get("msku_raw") or "",
                    "销售额（$）": row.get("target_sales_raw") or "",
                    "毛利润（$）": row.get("target_gross_profit_raw") or "",
                    "备注": row.get("remark_raw") or "",
                    "错误原因": row.get("error_message") or "",
                    "建议处理": row.get("suggestion") or "",
                }
            )
        return write_xlsx(headers=FAILED_HEADERS, rows=rows, sheet_name="失败明细")

    def _owner_row(self, row: RowMapping) -> OperationPlanOwnerRow:
        sales_target = Decimal(row["sales_target_amount"] or 0)
        gross_target = Decimal(row["gross_profit_target_amount"] or 0)
        sales_actual = Decimal(row["sales_actual_amount"] or 0)
        gross_actual = Decimal(row["gross_profit_actual_amount"] or 0)
        return OperationPlanOwnerRow(
            owner_ref=row.get("owner_ref"),
            owner_name=str(row.get("owner_name") or "未分配"),
            product_count=int(row["product_count"] or 0),
            sales_target_amount=sales_target,
            sales_actual_amount=sales_actual,
            sales_actual_qty=Decimal(row.get("sales_actual_qty") or 0),
            sales_completion_rate=_rate(sales_actual, sales_target),
            gross_profit_target_amount=gross_target,
            gross_profit_actual_amount=gross_actual,
            gross_profit_completion_rate=_rate(gross_actual, gross_target),
            lagging_count=int(row["lagging_count"] or 0),
            severe_lagging_count=int(row["severe_lagging_count"] or 0),
            stock_risk_count=int(row["stock_risk_count"] or 0),
        )

    def _product_row(self, row: RowMapping) -> OperationPlanProductRow:
        sales_target = Decimal(row["target_sales_amount"] or 0)
        gross_target = Decimal(row["target_gross_profit_amount"] or 0)
        sales_actual = Decimal(row.get("sales_actual_amount") or 0)
        sales_actual_qty = Decimal(row.get("sales_actual_qty") or 0)
        gross_actual = Decimal(row.get("gross_profit_actual_amount") or 0)
        last_sales = Decimal(row.get("last_sales_amount") or 0)
        last_profit = Decimal(row.get("last_gross_profit_amount") or 0)
        wfs_qty = Decimal(row.get("wfs_available_qty") or 0)
        inbound_qty = Decimal(row.get("inbound_qty") or 0)
        arriving_qty = Decimal(row.get("arriving_qty") or 0)

        available_qty = wfs_qty + inbound_qty + arriving_qty
        remaining_target_amount = max(Decimal("0"), sales_target - sales_actual)

        if remaining_target_amount <= 0:
            inventory_support_rate = Decimal("100.0")
        elif sales_actual_qty > 0 and sales_actual > 0:
            avg_sales_price = sales_actual / sales_actual_qty
            remaining_target_qty = remaining_target_amount / avg_sales_price
            inventory_support_rate = _rate(available_qty, remaining_target_qty)
        else:
            inventory_support_rate = Decimal("0")

        return OperationPlanProductRow(
            plan_id=row["id"],
            item_id=str(row["item_id"]),
            product_name=row.get("resolved_product_name") or row.get("product_name_snapshot"),
            sku=row.get("sku"),
            msku=str(row["msku"]),
            owner_ref=row.get("resolved_owner_ref") or row.get("owner_ref"),
            owner_name=row.get("resolved_owner_name") or row.get("owner_name_snapshot"),
            store_id=row.get("store_id"),
            store_name=row.get("store_name_snapshot"),
            last_sales_amount=last_sales,
            last_gross_profit_amount=last_profit,
            last_gross_profit_rate=_rate(last_profit, last_sales),
            sales_target_amount=sales_target,
            sales_actual_amount=sales_actual,
            sales_actual_qty=sales_actual_qty,
            sales_completion_rate=_rate(sales_actual, sales_target),
            sales_forecast_amount=Decimal(row.get("sales_forecast_amount") or 0),
            gross_profit_target_amount=gross_target,
            gross_profit_actual_amount=gross_actual,
            gross_profit_completion_rate=_rate(gross_actual, gross_target),
            gross_profit_forecast_amount=Decimal(row.get("gross_profit_forecast_amount") or 0),
            wfs_available_qty=wfs_qty,
            inbound_qty=inbound_qty,
            arriving_qty=arriving_qty,
            inventory_support_rate=inventory_support_rate,
            operation_status=row["operation_status"],
            plan_status=row["plan_status"],
            stock_status=(
                "risk"
                if (
                    row["stock_status"] == "risk"
                    or (remaining_target_amount > 0 and inventory_support_rate < Decimal("100"))
                )
                else row["stock_status"]
            ),
            adjusted=bool(row.get("adjusted")),
            event_count=int(row.get("event_count") or 0),
            remark=row.get("remark"),
        )


def template_xlsx() -> bytes:
    return write_xlsx(
        headers=TEMPLATE_HEADERS,
        rows=[
            {
                "商品ID": "20277220088",
                "MSKU": "YC00002-1A",
                "销售额（$）": "22000",
                "毛利润（$）": "4200",
                "备注": "本月重点商品",
            }
        ],
        sheet_name="计划模板",
    )


def parse_import_file(*, file_name: str, file_bytes: bytes) -> list[ParsedImportRow]:
    suffix = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
    if suffix == "csv":
        return _parse_csv(file_bytes)
    return _parse_xlsx(file_bytes)


def _parse_csv(file_bytes: bytes) -> list[ParsedImportRow]:
    text_content = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_content))
    rows: list[ParsedImportRow] = []
    for index, row in enumerate(reader, start=2):
        parsed = _dict_to_import_row(index, row)
        if _has_content(parsed):
            rows.append(parsed)
    return rows


def _parse_xlsx(file_bytes: bytes) -> list[ParsedImportRow]:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_path = _first_sheet_path(archive)
        xml = archive.read(sheet_path)
    root = ET.fromstring(xml)
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheet_rows: list[list[str]] = []
    for row in root.findall(".//main:sheetData/main:row", ns):
        values: dict[int, str] = {}
        for cell in row.findall("main:c", ns):
            ref = str(cell.attrib.get("r", "A1"))
            index = _column_index(ref)
            values[index] = _cell_value(cell, shared_strings, ns)
        if values:
            max_index = max(values)
            sheet_rows.append([values.get(i, "") for i in range(max_index + 1)])
    if not sheet_rows:
        return []
    headers = [item.strip() for item in sheet_rows[0]]
    rows: list[ParsedImportRow] = []
    for excel_row_number, values in enumerate(sheet_rows[1:], start=2):
        record = {headers[i]: values[i] if i < len(values) else "" for i in range(len(headers))}
        parsed = _dict_to_import_row(excel_row_number, record)
        if _has_content(parsed):
            rows.append(parsed)
    return rows


def _dict_to_import_row(row_number: int, row: dict[str, Any]) -> ParsedImportRow:
    return ParsedImportRow(
        row_number=row_number,
        item_id=_pick(row, "商品ID", "ItemID", "item_id"),
        msku=_pick(row, "MSKU", "msku"),
        sales_raw=_pick(row, "销售额（$）", "销售额（美金）", "sales_target_amount"),
        profit_raw=_pick(row, "毛利润（$）", "毛利润（美金）", "gross_profit_target_amount"),
        remark=_pick(row, "备注", "remark"),
    )


def _pick(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in row:
            return str(row.get(key) or "").strip()
    return ""


def _has_content(row: ParsedImportRow) -> bool:
    return any([row.item_id, row.msku, row.sales_raw, row.profit_raw, row.remark])


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        xml = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml)
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings: list[str] = []
    for item in root.findall("main:si", ns):
        text_parts = [node.text or "" for node in item.findall(".//main:t", ns)]
        strings.append("".join(text_parts))
    return strings


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    try:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    except KeyError:
        return "xl/worksheets/sheet1.xml"
    ns = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    sheet = workbook.find(".//main:sheets/main:sheet", ns)
    if sheet is None:
        return "xl/worksheets/sheet1.xml"
    rel_id = sheet.attrib.get(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    )
    if not rel_id:
        return "xl/worksheets/sheet1.xml"
    for rel in rels:
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib.get("Target", "worksheets/sheet1.xml").lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    return "xl/worksheets/sheet1.xml"


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return max(0, index - 1)


def _cell_value(cell: ET.Element, shared_strings: list[str], ns: dict[str, str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        text_nodes = cell.findall(".//main:t", ns)
        return "".join(node.text or "" for node in text_nodes).strip()
    value = cell.find("main:v", ns)
    if value is None or value.text is None:
        return ""
    raw = value.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(raw)].strip()
        except (IndexError, ValueError):
            return raw
    return raw


def write_xlsx(*, headers: list[str], rows: list[dict[str, Any]], sheet_name: str) -> bytes:
    sheet_xml = _worksheet_xml(headers=headers, rows=rows)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml(sheet_name))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/styles.xml", _styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return output.getvalue()


def _worksheet_xml(*, headers: list[str], rows: list[dict[str, Any]]) -> str:
    xml_rows = []
    all_rows = [dict(zip(headers, headers, strict=True)), *rows]
    for row_index, row in enumerate(all_rows, start=1):
        cells = []
        for col_index, header in enumerate(headers, start=1):
            ref = f"{_column_letter(col_index)}{row_index}"
            value = _xml_escape(str(row.get(header, "") if row.get(header, "") is not None else ""))
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheetData>{''.join(xml_rows)}</sheetData></worksheet>"
    )


def _column_letter(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _content_types_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">
<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>
<Default Extension=\"xml\" ContentType=\"application/xml\"/>
<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>
<Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>
<Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>
</Types>"""


def _root_rels_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>
</Relationships>"""


def _workbook_xml(sheet_name: str) -> str:
    safe_name = _xml_escape(sheet_name[:31] or "Sheet1")
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">
<sheets><sheet name=\"{safe_name}\" sheetId=\"1\" r:id=\"rId1\"/></sheets>
</workbook>"""


def _workbook_rels_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>
<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>
</Relationships>"""


def _styles_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><fonts count=\"1\"><font><sz val=\"11\"/><name val=\"Arial\"/></font></fonts><fills count=\"1\"><fill><patternFill patternType=\"none\"/></fill></fills><borders count=\"1\"><border/></borders><cellXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/></cellXfs></styleSheet>"""


def _parse_amount(raw: str, label: str, *, allow_zero: bool) -> tuple[Decimal | None, str | None]:
    text_value = str(raw or "").strip()
    if not text_value:
        return None, f"{label}不能为空"
    normalized = re.sub(r"[$,，\s]", "", text_value)
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None, f"{label}必须是数字"
    if allow_zero:
        if value < 0:
            return value, f"{label}不能小于 0"
    elif value <= 0:
        return value, f"{label}必须大于 0"
    return value.quantize(Decimal("0.01")), None


def _suggestion_for_errors(errors: list[str]) -> str:
    text_value = "；".join(errors)
    if "Listing" in text_value or "商品ID" in text_value or "MSKU" in text_value:
        return "请从 Listing 管理复制商品ID和MSKU，两个字段必须同时一致。"
    if "销售额" in text_value:
        return "销售额（$）填写大于 0 的美元数字，例如 22000。"
    if "毛利润" in text_value:
        return "毛利润（$）填写美元数字，例如 4200，且不能大于销售额。"
    return "请按模板修正后重新上传。"


def _rate(actual: Decimal, target: Decimal) -> Decimal:
    if target <= 0:
        return Decimal("0")
    return ((actual / target) * Decimal("100")).quantize(Decimal("0.1"))


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _period_dates(period_type: PeriodType, period_key: str) -> tuple[date, date]:
    if period_type == "month":
        year_text, month_text = period_key.split("-", 1)
        year = int(year_text)
        month = int(month_text)
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)
        return start, end
    year_text, quarter_text = period_key.split("-Q", 1)
    year = int(year_text)
    quarter = int(quarter_text)
    month = (quarter - 1) * 3 + 1
    start = date(year, month, 1)
    if quarter == 4:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 3, 1)
    return start, end


def _period_progress(period_type: PeriodType, period_key: str) -> Decimal:
    start, end = _period_dates(period_type, period_key)
    today = datetime.now(UTC).date()
    total_days = max(1, (end - start).days)
    elapsed_days = min(max(0, (today - start).days + 1), total_days)
    return ((Decimal(elapsed_days) / Decimal(total_days)) * Decimal("100")).quantize(Decimal("0.1"))
