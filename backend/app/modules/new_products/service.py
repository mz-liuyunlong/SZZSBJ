"""Scoped new-product use cases. Existing sales, advertising and cost facts are read-only."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, tuple_
from sqlalchemy.orm import Session

from app.core.api import ApiError

from . import rules
from .bulk_read import (
    EMPTY_ADS,
    EMPTY_ORDERS,
    ReadSnapshot,
    load_read_snapshot,
)
from .models import ActionEvent, MarketScore, PurchaseApplication, RuleVersion, TrackingDecision
from .persisted_projection import load_persisted_page, merge_persisted_page_row
from .persisted_read import load_persisted, snapshot_row  # PR337_PERSISTED_DISPLAY_V1
from .repository import NewProductRepository
from .sale_stat_order_evidence import reconcile_sale_stat_order_evidence
from .scoring import evaluate
from .testing_profit import FINAL_RESULTS, load_final_decisions, load_testing_profit_page
from .testing_profit_projection import (
    attach_testing_profit_facts,
    closed_list_row,
    closed_score,
    update_list_profit,
)

LA = ZoneInfo("America/Los_Angeles")
_LOGGER = logging.getLogger(__name__)
_MARKET_UNSET = object()


def problem(code: str, status: int, message: str):
    raise ApiError(code=code, status_code=status, message=message)


def serialized(obj):
    return json.loads(json.dumps(obj, default=str, ensure_ascii=False))


def ident(obj):
    return (obj.source_account_ref, obj.store_id, obj.item_id)


def local_preview_item_ids() -> frozenset[str] | None:
    """Opt-in temporary evaluation of exactly four requested Item IDs.

    Production remains strictly unaffected. Never persist this preview.
    """
    value = os.getenv("PR337_LOCAL_PREVIEW_ITEM_IDS", "").strip()
    if not value:
        return None
    if os.getenv("APP_ENV", "").strip().lower() not in ("local", "dev", "development"):
        problem("NEW_PRODUCT_PREVIEW_LOCAL_ONLY", 403, "四商品试算只允许本地开发环境")
    ids = [piece.strip() for piece in value.split(",")]
    if len(ids) != 4 or len(set(ids)) != 4 or any(not x.isascii() or not x.isdigit() for x in ids):
        problem("NEW_PRODUCT_PREVIEW_INVALID", 422, "测试商品必须是四个不重复的 Item ID")
    return frozenset(ids)


class NewProductService:
    def __init__(self, session: Session, *, read_session: Session | None = None):
        self.db = session
        self.repo = NewProductRepository(read_session or session)
        self.write_repo = NewProductRepository(session)

    def _listing(self, accounts, account, store, item):
        listing = self.repo.exact_listing(accounts, account, store, item)
        if listing is None:
            problem("NEW_PRODUCT_NOT_FOUND", 404, "未找到具有小批量测品标签的商品或无权限访问")
        return listing

    def rule(self, kind):
        row = self.write_repo.rule_version(kind)
        return {
            "kind": kind,
            "version": row.version if row else 0,
            "config": row.config_json if row else None,
            "source": "database" if row else "default",
            "applied_at": row.applied_at if row else None,
            "applied_by": row.applied_by if row else None,
        }

    def apply_rule(self, kind, expected_version, config, actor, change_reason):
        try:
            rules.validate(kind, config)
        except (ValueError, KeyError, TypeError) as e:
            problem("NEW_PRODUCT_RULE_INVALID", 422, str(e))
        try:
            # Serialize one kind's publication within the active PostgreSQL transaction.
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "PR337_NEW_PRODUCT_RULE_" + kind},
            )
            current = self.write_repo.rule_version(kind)
            version = current.version if current else 0
            if expected_version != version:
                problem("NEW_PRODUCT_RULE_CONFLICT", 409, "规则版本发生变化，请刷新后保存")
            if current and current.config_json == config:
                return {
                    "kind": kind,
                    "version": version,
                    "config": current.config_json,
                    "unchanged": True,
                    "applied_at": current.applied_at,
                }
            row = RuleVersion(
                id=uuid4(),
                kind=kind,
                version=version + 1,
                config_json=serialized(config),
                applied_at=datetime.now(UTC),
                applied_by=actor,
                change_reason=change_reason.strip(),
            )
            self.db.add(row)
            self.db.commit()
            return {
                "kind": kind,
                "version": row.version,
                "config": row.config_json,
                "unchanged": False,
                "applied_at": row.applied_at,
            }
        except Exception:
            self.db.rollback()
            raise

    def rule_history(self, kind, limit, offset):
        rows, total = self.write_repo.rule_history(kind, limit, offset)
        return {
            "items": [
                {
                    "kind": row.kind,
                    "version": row.version,
                    "config": row.config_json,
                    "applied_at": row.applied_at,
                    "applied_by": row.applied_by,
                    "change_reason": row.change_reason,
                }
                for row in rows
            ],
            "total": total,
        }

    def _facts(
        self,
        account,
        store,
        item,
        market_score=_MARKET_UNSET,
        *,
        snapshot: ReadSnapshot | None = None,
    ):
        today = datetime.now(LA).date()
        key = (account, store, item)
        lock = (
            snapshot.first.get(key)
            if snapshot is not None
            else self.repo.first_wfs_date(account, store, item)
        )
        start = lock["day"] if lock is not None else None
        first_source = lock["date_source"] if lock is not None else None
        # 14 inclusive calendar dates: day 1 = first WFS positive LA date.
        end = start + timedelta(days=13) if start else None
        elapsed = max(0, (today - start).days + 1) if start else None
        if snapshot is None:
            orders = self.repo.order_summary(account, store, item, start, end) if start else None
            rows = (
                self.repo.daily_series(account, store, item, start, min(end, today))
                if start
                else []
            )
            ads = (
                self.repo.ads(account, store, item, start, min(end, today))
                if start
                else dict(EMPTY_ADS)
            )
        else:
            orders = snapshot.orders.get(key, EMPTY_ORDERS) if start else None
            rows = snapshot.daily.get(key, []) if start else []
            ads = snapshot.ads.get(key, EMPTY_ADS) if start else dict(EMPTY_ADS)
        # PR337_SALESTAT_SPEED_FACT_TRUST_20261114
        # Paid SaleStat is the speed source. Canonical FACT contributes trust
        # only when its order and unit totals reconcile; legacy versions are
        # not promoted to current identity or counted as independent lines.
        order_evidence = reconcile_sale_stat_order_evidence(
            first_wfs_day=start, daily_rows=rows, canonical_orders=orders
        )
        # PR337_MART_AUTHORITY_DETAIL_SCORE_V3_20261115
        # DETAIL/SCORE ONLY: local read-only true purchase day / historical
        # line proof. Batch list remains in reconcile_pending_rows after
        # snapshot projection; preview MUST keep its one bounded snapshot.
        if (
            snapshot is None
            and start is not None
            and end is not None
            and end < today
            and rows
            and not order_evidence.fact_reconciled
            and os.getenv("APP_ENV", "").strip().lower() in {"local", "dev", "development"}
        ):
            from dataclasses import replace

            from .order_lineage_view import read_paid_order_summary

            paid = read_paid_order_summary(
                self.repo.session, str(account), str(store), str(item), start, end, rows
            )
            if paid is not None:
                order_evidence = replace(
                    order_evidence,
                    effective_orders=paid["orders"],
                    first_order_day=(paid["first_date"] - start).days + 1,
                    valid_orders=paid["orders"],
                    valid_units=Decimal(paid["units"]),
                    single_orders=paid["singles"],
                    fact_reconciled=True,
                    reason="MART_PAID_ORDER_DISTRIBUTION_RECONCILED_V3",
                )
        fact_unknown = not order_evidence.fact_reconciled
        # PR337_MART_ONLY_DETAIL_V4_20261115
        if (
            snapshot is None
            and start is not None
            and end is not None
            and end < today
            and rows
            and os.getenv("APP_ENV", "").strip().lower() in {"local", "dev", "development"}
        ):
            from dataclasses import replace as _pr337_replace

            from .mart_only_v4 import mart_deterministic_evidence

            _mart_only = mart_deterministic_evidence(start, end, rows)
            if _mart_only is not None:
                order_evidence = _pr337_replace(
                    order_evidence,
                    effective_orders=_mart_only["orders"],
                    first_order_day=(_mart_only["first_date"] - start).days + 1,
                    valid_orders=_mart_only["orders"],
                    valid_units=Decimal(_mart_only["units"]),
                    single_orders=_mart_only["singles"],
                    fact_reconciled=True,
                    reason="MART_DAILY_SINGLE_COUNTS_PROVEN_V4",
                )
                fact_unknown = False
        ad_status = "unknown"
        # Display separately verified lifetime USD spend/clicks even when
        # attribution is incomplete; never promote those to a valid ad score.
        spend_ok = bool(ads["n"]) and not ads.get("spend_missing", ads["incomplete"])
        clicks_ok = bool(ads["n"]) and not ads.get("clicks_missing", ads["incomplete"])
        if (
            ads["n"]
            and not ads["incomplete"]
            and ads["spend"] is not None
            and Decimal(str(ads["spend"])) > 0
        ):
            ad_status = "active"
        # Note: no ad rows are NOT proof of no advertising. No 'not_run' inference.
        roi = None
        margin = None
        if rows and all(
            row["cost_status"] == "complete"
            and row["gross_profit_amount"] is not None
            and row.get("sales_currency_code") == "USD"
            and row.get("gross_profit_currency_code") == "USD"
            and row["sales_amount"] is not None
            and row["purchase_cost_total_usd"] is not None
            and row["first_leg_cost_total_usd"] is not None
            for row in rows
        ):
            profits = sum((Decimal(str(x["gross_profit_amount"])) for x in rows), Decimal(0))
            revenue = sum((Decimal(str(x["sales_amount"])) for x in rows), Decimal(0))
            cost = sum(
                (
                    Decimal(str(x["purchase_cost_total_usd"]))
                    + Decimal(str(x["first_leg_cost_total_usd"]))
                    for x in rows
                ),
                Decimal(0),
            )
            if revenue > 0:
                margin = profits / revenue * 100
            if cost > 0:
                roi = profits / cost
        market = (
            self.write_repo.market(account, store, item)
            if market_score is _MARKET_UNSET
            else market_score
        )
        first_day = order_evidence.first_order_day
        valid_orders = order_evidence.valid_orders
        units = order_evidence.valid_units
        single = order_evidence.single_orders
        return {
            "source_account_ref": account,
            "store_id": store,
            "item_id": item,
            "first_wfs_available_date_la": start,
            "first_wfs_date_source": first_source,
            "observation_end_la": end,
            "elapsed_days": elapsed,
            "first_order_day": first_day,
            "effective_orders_14d": order_evidence.effective_orders,
            "valid_orders_14d": valid_orders,
            "valid_units_14d": units,
            "single_unit_orders_14d": single,
            "market_score": market.score if isinstance(market, MarketScore) else market,
            "ad_status": ad_status,
            "ad_spend_usd": ads["spend"] if spend_ok else None,
            "ad_clicks": ads["clicks"] if clicks_ok else None,
            "ad_orders": ads["orders"] if ad_status == "active" else None,
            "ad_revenue_usd": ads["revenue"] if ad_status == "active" else None,
            "ad_latest_sync": ads["latest_sync"],
            "roi": roi,
            "gross_margin_pct": margin,
            "profit_source": "mart_daily_sales_item_day"
            if roi is not None
            else "missing_or_incomplete",
            "b1_contribution_profit_usd": None,
            "b1_source_status": "not_verified",
            "data_cutoff_la": min(end, today) if end else None,
            "data_status": "partial" if fact_unknown or not start or roi is None else "available",
        }

    def _config(self):
        row = self.write_repo.rule_version("performance")
        if row:
            return row.config_json, row.version
        # The confirmed business defaults are truthful; the editable complete rule
        # still needs a first 'save and apply' action to publish version 1.
        return {
            "weights": rules.DEFAULT_WEIGHTS,
            "confirmedScoring": rules.DEFAULT_PARAMETERS,
            "gradeBands": {
                "S": [9, 10],
                "A": [8, 8.99],
                "B": [7, 7.99],
                "C": [6, 6.99],
                "D": [0, 5.99],
            },
            "quantityStrategy": "mid",
            "scoreCriteria": {},
            "penalties": [],
            "vetoes": [
                {"name": "ROI 低（Pass）", "enabled": True},
                {"name": "ROI 低（评级上限）", "enabled": True},
                {"name": "毛利率过低", "enabled": True},
            ],
            "quantities": {
                "S": [400, 600],
                "A": [300, 500],
                "B": [200, 400],
                "C": [150, 250],
                "D": [0, 0],
                "Pass": [0, 0],
            },
        }, 0

    def _final_decisions(self, keys):
        final = load_final_decisions(self.repo.session, keys)
        if self.db is not self.repo.session:
            local = load_final_decisions(self.db, keys)
            for key, state in local.items():
                if key in final and final[key].result != state.result:
                    raise ValueError("Conflicting final testing results across sources")
                if key not in final or state.snapshot is not None:
                    final[key] = state
        return final

    def score(self, accounts, account, store, item, *, custom_config=None):
        self._listing(accounts, account, store, item)
        key = (account, store, item)
        final = self._final_decisions([key]).get(key)
        if final is not None:
            saved = load_persisted_page(self.repo.session, [key])
            return closed_score(key, saved.get(key), final, datetime.now(LA).date())
        f = self._facts(account, store, item)
        cutoff = datetime.now(LA).date() - timedelta(days=1)
        profit = load_testing_profit_page(self.repo.session, [key], cutoff).get(key)
        attach_testing_profit_facts(f, profit)
        config, version = self._config() if custom_config is None else (custom_config, -1)
        result = evaluate(f, config, version)
        return {
            "identity": {"source_account_ref": account, "store_id": store, "item_id": item},
            "facts": serialized(f),
            "evaluation": result,
            "rule_source": "database" if version > 0 else "confirmed_defaults",
            "rule_version": version,
        }

    def list(self, accounts, query):
        """Fail-safe cutover: preserve current preview/score behavior by default.

        Saved-only mode is an explicit *local* opt-in after daily snapshots
        have been inspected. Never change production semantics implicitly.
        """
        # PR337_LOCAL_PREVIEW_DISPATCH_EXACT_V5_20261115
        # Explicit four-item preview must use the old bounded snapshot path.
        # Production still fails closed in local_preview_item_ids().
        if os.getenv("PR337_LOCAL_PREVIEW_ITEM_IDS", "").strip():
            return self._list_legacy_live(accounts, query)
        if os.getenv("APP_ENV", "").strip().lower() in {
            "local",
            "dev",
            "development",
        } and os.getenv("SZZSBJ_NEW_PRODUCT_SAVED_LIST_ONLY", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return self._list_saved(accounts, query)
        return self._list_legacy_live(accounts, query)

    def _list_saved(self, accounts, query):
        """List saved results only. No advertising, order, profit or scoring queries.

        All expensive evidence/score calculations belong to background publishers.
        Missing saved evidence is represented as unavailable, never invented.
        """
        from .ad_display_snapshot import load_saved_ad_display, overlay_saved_ad_display

        started = time.monotonic()
        try:
            preview = local_preview_item_ids()
            filters = {"item_ids": preview} if preview is not None else {}
            data, total, last = self.repo.page(
                accounts,
                page=query.page,
                page_size=query.page_size,
                store_id=query.store_id,
                owner=query.owner,
                keyword=query.keyword,
                search_field=query.search_field,
                status=query.status,
                **filters,
            )
            if preview is not None and total > 4:
                raise ValueError("本地四商品试算范围超过四条，已停止")
            keys = [ident(listing) for listing in data.items]
            persisted = load_persisted(self.repo.session, keys) if keys else {}
            finals = self._final_decisions(keys) if keys else {}
            market_scores = {}
            if keys and persisted:
                market_scores = {
                    ident(m): m
                    for m in self.db.scalars(
                        select(MarketScore).where(
                            tuple_(
                                MarketScore.source_account_ref,
                                MarketScore.store_id,
                                MarketScore.item_id,
                            ).in_(keys)
                        )
                    ).all()
                }
            saved_ads = load_saved_ad_display(self.db, keys)
            today_la = datetime.now(LA).date()
            rows = []
            for listing in data.items:
                key = ident(listing)
                if key in finals:
                    row = closed_list_row(
                        listing.model_dump(mode="json"),
                        persisted.get(key),
                        finals[key],
                        today_la,
                    )
                else:
                    row = snapshot_row(
                        listing,
                        None,
                        persisted.get(key),
                        market_scores.get(key),
                        today_la,
                    )
                    merge_persisted_page_row(row, persisted.get(key), today_la)
                    # Display-only fields from the writable new-product snapshot.
                    # No raw/source-table query or score calculation occurs here.
                    if key in saved_ads:
                        overlay_saved_ad_display(row, saved_ads[key])
                    elif key in persisted and persisted[key][1] is not None:
                        coverage = persisted[key][1].data_coverage_json
                        if isinstance(coverage, dict):
                            overlay_saved_ad_display(row, coverage.get("ad_display_v1"))
                rows.append(row)
            _LOGGER.info(
                "new_product_list_saved_only page=%d count=%d total=%d elapsed_ms=%d",
                query.page,
                len(rows),
                total,
                int((time.monotonic() - started) * 1000),
            )
            return {
                "items": rows,
                "total": total,
                "page": query.page,
                "page_size": query.page_size,
                "tag_filter": "小批量测品",
                "last_listing_calculated_at": last,
                "rule_version": 0,
                "local_preview": preview is not None,
            }
        except Exception as exc:
            _LOGGER.warning(
                "new_product_list_failed stage=saved_listing_page error_type=%s elapsed_ms=%d",
                type(exc).__name__,
                int((time.monotonic() - started) * 1000),
            )
            raise

    def _list_legacy_live(self, accounts, query):
        """Normal list requests do not score. Four-item local preview is opt-in.

        Production must use precomputed background snapshots instead of the
        local-only request-time evaluation exception.
        """
        started = time.monotonic()
        try:
            preview = local_preview_item_ids()
            kwargs = {"item_ids": preview} if preview is not None else {}
            data, total, last = self.repo.page(
                accounts,
                page=query.page,
                page_size=query.page_size,
                store_id=query.store_id,
                owner=query.owner,
                keyword=query.keyword,
                search_field=query.search_field,
                status=query.status,
                **kwargs,
            )
            if preview is not None and total > 4:
                raise ValueError("本地四商品试算范围超过四条，已停止")
            # Daily sales is already aggregated upstream. Read first positive
            # order day in one bounded query for this page.
            first_orders = self.repo.first_order_dates(data.items)
            page_keys = [ident(item) for item in data.items]
            finals = self._final_decisions(page_keys)
            open_keys = [key for key in page_keys if key not in finals]
            cutoff_la = datetime.now(LA).date() - timedelta(days=1)
            profit_page = (
                load_testing_profit_page(self.repo.session, open_keys, cutoff_la)
                if open_keys
                else {}
            )
            profit_config, _ = self._config()
            # One read-only, page-scoped SELECT; no per-product score calculation.
            persisted = (
                load_persisted_page(self.repo.session, [ident(item) for item in data.items])
                if preview is None
                else {}
            )
            rows = []
            today_la = datetime.now(LA).date()
            snapshot = None
            config = None
            version = 0
            market_scores = {}
            persisted = {}
            if preview is None and data.items:
                keys = [ident(item) for item in data.items]
                persisted = load_persisted(self.repo.session, keys)
                if persisted:
                    market_scores = {
                        ident(row): row
                        for row in self.db.scalars(
                            select(MarketScore).where(
                                tuple_(
                                    MarketScore.source_account_ref,
                                    MarketScore.store_id,
                                    MarketScore.item_id,
                                ).in_(keys)
                            )
                        ).all()
                    }
            if preview is not None and data.items:
                keys = [ident(item) for item in data.items]
                snapshot = load_read_snapshot(
                    self.repo.session, keys, today_la, preview_since_first=True
                )
                config, version = self._config()
                # Read only already stored market scores from the local test DB.
                market_scores = {
                    ident(row): row
                    for row in self.db.scalars(
                        select(MarketScore).where(
                            tuple_(
                                MarketScore.source_account_ref,
                                MarketScore.store_id,
                                MarketScore.item_id,
                            ).in_(keys)
                        )
                    ).all()
                }
            for listing in data.items:
                record = listing.model_dump(mode="json")
                key = ident(listing)
                if key in finals:
                    rows.append(closed_list_row(record, persisted.get(key), finals[key], today_la))
                    continue
                first_date = first_orders.get(
                    (record["source_account_ref"], record["store_id"], record["item_id"])
                )
                first_day = listing.first_wfs_available_date_la
                # Calendar day 1 is the real first positive WFS stock date.
                # This is a display field, not a scoring or daily-compute run.
                if snapshot is not None:
                    key = ident(listing)
                    facts = self._facts(
                        *key, market_score=market_scores.get(key), snapshot=snapshot
                    )
                    # PR337_LOCAL_PREVIEW_EMPTY_ORDERS_COMPAT_V2_20261115
                    # Preserve the original explicit empty-snapshot test contract
                    # ONLY for local preview, never for saved/live scoring.
                    if (
                        preview is not None
                        and key not in snapshot.orders
                        and not snapshot.daily.get(key)
                        and facts.get("effective_orders_14d") is None
                        and facts.get("valid_orders_14d") is None
                        and facts.get("valid_units_14d") is None
                        and facts.get("single_unit_orders_14d") is None
                    ):
                        facts["effective_orders_14d"] = 0
                        facts["valid_orders_14d"] = 0
                        facts["single_unit_orders_14d"] = 0
                    facts["first_order_date"] = first_date.isoformat() if first_date else None
                    facts["orders_7d"] = snapshot.recent_orders.get(key, 0) if first_day else None
                    attach_testing_profit_facts(facts, profit_page.get(key))
                    evaluation = evaluate(facts, config, version)
                    rows.append(
                        {
                            "listing": record,
                            "facts": serialized(facts),
                            "evaluation": evaluation,
                            "market_reason": market_scores[key].reason
                            if key in market_scores
                            else None,
                            "market_version": market_scores[key].version
                            if key in market_scores
                            else 0,
                            "purchase_status": None,
                            "purchase_id": None,
                            "tracking_decision": None,
                            "tracking_reason": None,
                            "system_recommendation": self.system_recommendation(facts, evaluation),
                            "suggested_qty": self._suggested_quantity(evaluation, config),
                        }
                    )
                    continue
                rows.append(
                    snapshot_row(
                        listing,
                        first_date,
                        persisted.get(ident(listing)),
                        market_scores.get(ident(listing)),
                        today_la,
                    )
                )
                if preview is None:
                    merge_persisted_page_row(rows[-1], persisted.get(ident(listing)), today_la)
                    update_list_profit(rows[-1], profit_page.get(key), profit_config)
            _LOGGER.info(
                "new_product_list_read_only page=%d count=%d total=%d elapsed_ms=%d",
                query.page,
                len(rows),
                total,
                int((time.monotonic() - started) * 1000),
            )
            # PR337_NEW_PRODUCTS_UNIFIED_RECONCILE_V2_20261115 - new-products-only local read view
            if preview is None:
                # PR337_MART_ONLY_DETERMINISTIC_V4_20261115
                # Independent SaleStat proof comes FIRST; no Order V2 read for
                # rows whose daily singles are mathematically determined.
                from .mart_only_v4 import reconcile_mart_only_pending_rows

                reconcile_mart_only_pending_rows(self.repo.session, rows)
                from .order_lineage_view import reconcile_pending_rows

                reconcile_pending_rows(self.repo.session, rows)
                # PR337_MART_TRUST_FINALIZE_V6_20261115
                # Fill ONLY missing trust after existing V3/V4/V5 read-only logic.
                from .mart_trust_finalize_v6 import finalize_missing_mart_trust

                finalize_missing_mart_trust(self.repo.session, rows)
            # PR337_DAILY_PERSIST_V1: only the normal list reads saved facts.
            if preview is None:
                from .pr337_daily_view import saved_daily_view

                for saved_row in rows:
                    listing_row = saved_row.get("listing", {})
                    key = tuple(
                        str(listing_row.get(k) or "")
                        for k in ("source_account_ref", "store_id", "item_id")
                    )
                    saved_daily_view(saved_row, persisted.get(key))
            return {
                "items": rows,
                "total": total,
                "page": query.page,
                "page_size": query.page_size,
                "tag_filter": "小批量测品",
                "last_listing_calculated_at": last,
                "rule_version": version,
                "local_preview": preview is not None,
            }
        except Exception as exc:
            _LOGGER.warning(
                "new_product_list_failed stage=listing_page error_type=%s elapsed_ms=%d",
                type(exc).__name__,
                int((time.monotonic() - started) * 1000),
            )
            raise

    @staticmethod
    def _suggested_quantity(evaluation: dict, config: dict):
        grade = evaluation.get("grade")
        if not grade or grade in ("D", "Pass"):
            return None
        bounds = config.get("quantities", {}).get(grade)
        if not isinstance(bounds, list) or len(bounds) != 2:
            return None
        strategy = config.get("quantityStrategy", "mid")
        return (
            bounds[0] if strategy == "min" else bounds[1] if strategy == "max" else sum(bounds) // 2
        )

    @staticmethod
    def system_recommendation(f: dict, evaluation: dict):
        if f["first_wfs_available_date_la"] is None:
            return {"value": "暂无法判定", "reasons": ["首次可售日缺失"]}
        if f.get("effective_orders_14d") == 0 and f.get("elapsed_days") is not None:
            return {"value": "建议继续观察", "reasons": ["观察期未产生有效订单；不自动判定失败"]}
        if f.get("b1_contribution_profit_usd") is None:
            return {
                "value": "暂无法判定",
                "reasons": ["B1贡献利润权威数据尚未核实，不使用毛利润代替"],
            }
        return {"value": "暂无法判定", "reasons": ["缺少完整的系统建议业务依据"]}

    def persisted_score(self, accounts, account, store, item):
        """Saved GET snapshot; write workflows still use live score() unchanged."""
        listing = self._listing(accounts, account, store, item)
        key = ident(listing)
        saved = load_persisted(self.repo.session, [key]).get(key)
        first_order = self.repo.first_order_dates([listing]).get(key)
        market = self.write_repo.market(account, store, item) if saved is not None else None
        row = snapshot_row(listing, first_order, saved, market, datetime.now(LA).date())
        # PR337_DAILY_PERSIST_V1: detail GET reads saved evidence.
        from .pr337_daily_view import saved_daily_view

        saved_daily_view(row, saved)
        return {
            "identity": {
                "source_account_ref": account,
                "store_id": store,
                "item_id": item,
            },
            "listing": row["listing"],
            "facts": row["facts"],
            "evaluation": row["evaluation"],
            "rule_source": "persisted_snapshot",
            "rule_version": row["evaluation"]["rule_version"],
        }

    def detail(self, accounts, account, store, item):
        self._listing(accounts, account, store, item)
        score = self.persisted_score(accounts, account, store, item)
        tr = self.write_repo.tracking(account, store, item)
        if score.get("rule_source") == "frozen_snapshot":
            series = []
        else:
            end = datetime.now(LA).date()
            start = end - timedelta(days=179)
            series = self.repo.daily_series(account, store, item, start, end)
        return {
            "listing": score["listing"],
            "score": score,
            "sales_series": serialized(series),
            "tracking_decision": tr.decision if tr else None,
            "tracking_reason": tr.reason if tr else None,
            "events": [
                {
                    "type": e.event_type,
                    "actor": e.actor_id,
                    "at": e.created_at,
                    "payload": e.payload_json,
                }
                for e in self.write_repo.events(account, store, item)
            ],
            "system_recommendation": {"value": "暂无法判定", "reasons": ["系统建议尚未计算"]},
        }

    def preview(self, accounts, account, store, item, config):
        try:
            rules.validate("performance", config)
        except (ValueError, KeyError, TypeError) as e:
            problem("NEW_PRODUCT_RULE_INVALID", 422, str(e))
        return self.score(accounts, account, store, item, custom_config=config)

    def _event(self, account, store, item, type_, actor, payload):
        self.db.add(
            ActionEvent(
                id=uuid4(),
                source_account_ref=account,
                store_id=store,
                item_id=item,
                event_type=type_,
                actor_id=actor,
                payload_json=serialized(payload),
                created_at=datetime.now(UTC),
            )
        )

    def save_market(self, accounts, body, actor):
        a, s, i = ident(body)
        self._listing(accounts, a, s, i)
        try:
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "PR337_MARKET_" + a + ":" + s + ":" + i},
            )
            row = self.write_repo.market(a, s, i)
            v = row.version if row else 0
            if body.expected_version != v:
                problem("NEW_PRODUCT_MARKET_CONFLICT", 409, "市场评分已被其他人员更新")
            if row:
                row.score = body.score
                row.reason = body.reason.strip()
                row.version += 1
                row.updated_by = actor
                row.updated_at = datetime.now(UTC)
            else:
                row = MarketScore(
                    id=uuid4(),
                    source_account_ref=a,
                    store_id=s,
                    item_id=i,
                    score=body.score,
                    reason=body.reason.strip(),
                    version=1,
                    updated_by=actor,
                    updated_at=datetime.now(UTC),
                )
                self.db.add(row)
            # PR337_MANUAL_RISK_V1: audit the explicit human risk selection.
            self._event(
                a,
                s,
                i,
                "market_score",
                actor,
                {
                    **{"score": body.score, "reason": body.reason.strip(), "version": v + 1},
                    "risk_conditions": list(body.risk_conditions),
                },
            )
            self.db.commit()
            return {"version": v + 1, "score": body.score, "reason": row.reason}
        except Exception:
            self.db.rollback()
            raise

    def purchase(self, accounts, body, actor):
        a, s, i = ident(body)
        self._listing(accounts, a, s, i)
        current = self.score(accounts, a, s, i)
        ev = current["evaluation"]
        cfg, version = self._config()
        if ev["grade"] is None or ev["grade"] in ("D", "Pass"):
            problem("NEW_PRODUCT_PURCHASE_BLOCKED", 409, "关键指标缺失、被否决或不符合采购评级")
        if body.expected_rule_version != version:
            problem("NEW_PRODUCT_RULE_CONFLICT", 409, "评分规则已更新，请重新计算")
        suggested = self._suggested_quantity(ev, cfg)
        if suggested is None:
            problem("NEW_PRODUCT_PURCHASE_BLOCKED", 409, "无有效采购建议")
        if body.requested_qty != suggested and len(body.reason.strip()) < 5:
            problem("NEW_PRODUCT_PURCHASE_REASON_REQUIRED", 422, "调整采购数量必须填写至少5字原因")
        try:
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "PR337_PURCHASE_" + a + ":" + s + ":" + i},
            )
            if self.write_repo.active_purchase(a, s, i, lock=True):
                problem("NEW_PRODUCT_PURCHASE_PENDING", 409, "商品存在进行中的采购申请")
            row = PurchaseApplication(
                id=uuid4(),
                source_account_ref=a,
                store_id=s,
                item_id=i,
                status="submitted",
                version=1,
                requested_qty=body.requested_qty,
                suggested_qty=suggested,
                request_reason=body.reason.strip(),
                score_snapshot=serialized(current),
                score_rule_version=version,
                applicant_id=actor,
                created_at=datetime.now(UTC),
            )
            self.db.add(row)
            self._event(
                a,
                s,
                i,
                "purchase_submitted",
                actor,
                {
                    "application_id": str(row.id),
                    "requested_qty": body.requested_qty,
                    "rule_version": version,
                },
            )
            self.db.commit()
            return {"application_id": str(row.id), "status": row.status, "version": row.version}
        except Exception:
            self.db.rollback()
            raise

    def approvals(self, accounts, *, page=1, page_size=50, status="submitted"):
        stmt = select(PurchaseApplication).where(
            PurchaseApplication.source_account_ref.in_(accounts)
        )
        if status:
            stmt = stmt.where(PurchaseApplication.status == status)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(
            stmt.order_by(PurchaseApplication.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {
            "items": [
                {
                    "id": str(r.id),
                    "source_account_ref": r.source_account_ref,
                    "store_id": r.store_id,
                    "item_id": r.item_id,
                    "status": r.status,
                    "version": r.version,
                    "requested_qty": r.requested_qty,
                    "suggested_qty": r.suggested_qty,
                    "reason": r.request_reason,
                    "rule_version": r.score_rule_version,
                    "score_snapshot": r.score_snapshot,
                    "applicant": r.applicant_id,
                    "created_at": r.created_at,
                    "reviewed_by": r.reviewed_by,
                    "reviewed_at": r.reviewed_at,
                    "review_reason": r.review_reason,
                }
                for r in rows
            ],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }

    def decide_purchase(self, accounts, approval_id, body, actor):
        try:
            row = self.db.scalar(
                select(PurchaseApplication)
                .where(
                    PurchaseApplication.id == approval_id,
                    PurchaseApplication.source_account_ref.in_(accounts),
                )
                .with_for_update()
            )
            if not row:
                problem("NEW_PRODUCT_APPROVAL_NOT_FOUND", 404, "申请不存在")
            if row.status != "submitted" or row.version != body.expected_version:
                problem("NEW_PRODUCT_APPROVAL_CONFLICT", 409, "申请已被处理或版本已变化")
            if row.applicant_id == actor:
                problem("NEW_PRODUCT_SELF_REVIEW", 403, "不能审核自己提交的申请")
            if body.decision == "rejected" and len(body.reason.strip()) < 5:
                problem("NEW_PRODUCT_REJECTION_REASON_REQUIRED", 422, "驳回原因至少5字")
            row.status = body.decision
            row.version += 1
            row.reviewed_by = actor
            row.reviewed_at = datetime.now(UTC)
            row.review_reason = body.reason.strip()
            self._event(
                row.source_account_ref,
                row.store_id,
                row.item_id,
                "purchase_" + body.decision,
                actor,
                {
                    "application_id": str(row.id),
                    "reason": row.review_reason,
                    "snapshot_rule_version": row.score_rule_version,
                },
            )
            self.db.commit()
            return {"id": str(row.id), "status": row.status, "version": row.version}
        except Exception:
            self.db.rollback()
            raise

    def save_tracking(self, accounts, body, actor):
        a, s, i = ident(body)
        self._listing(accounts, a, s, i)
        if body.decision in ("打品失败", "需要优化") and len(body.reason.strip()) < 5:
            problem(
                "NEW_PRODUCT_TRACKING_REASON_REQUIRED", 422, "失败或需优化时必须填写至少5字原因"
            )
        if self._final_decisions([(a, s, i)]).get((a, s, i)) is not None:
            problem("NEW_PRODUCT_TRACKING_FINAL_LOCKED", 409, "Final testing result is locked")
        first = self.repo.first_wfs_date(a, s, i)
        if not first:
            problem("NEW_PRODUCT_TRACKING_NOT_STARTED", 409, "WFS首次可售证据缺失，不能人工判定")
        score = self.score(accounts, a, s, i)
        try:
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "PR337_TRACKING_" + a + ":" + s + ":" + i},
            )
            if self._final_decisions([(a, s, i)]).get((a, s, i)) is not None:
                problem("NEW_PRODUCT_TRACKING_FINAL_LOCKED", 409, "Final testing result is locked")
            row = self.write_repo.tracking(a, s, i)
            v = row.version if row else 0
            if body.expected_version != v:
                problem("NEW_PRODUCT_TRACKING_CONFLICT", 409, "打品结果已被其他用户修改")
            if row and row.decision in ("打品成功", "打品失败"):
                problem("NEW_PRODUCT_TRACKING_FINAL_LOCKED", 409, "最终打品结果已锁定")
            rv = self.write_repo.rule_version("tracking")
            ver = rv.version if rv else 0
            captured = serialized(score["facts"])
            if body.decision in FINAL_RESULTS:
                captured["__test_final_score_v2"] = serialized(score)
            if row:
                row.decision = body.decision
                row.reason = body.reason.strip()
                row.version += 1
                row.rule_version = ver
                row.evaluated_facts = captured
                row.decided_by = actor
                row.decided_at = datetime.now(UTC)
            else:
                row = TrackingDecision(
                    id=uuid4(),
                    source_account_ref=a,
                    store_id=s,
                    item_id=i,
                    decision=body.decision,
                    reason=body.reason.strip(),
                    version=1,
                    rule_version=ver,
                    evaluated_facts=captured,
                    decided_by=actor,
                    decided_at=datetime.now(UTC),
                )
                self.db.add(row)
            self._event(
                a,
                s,
                i,
                "tracking_decision",
                actor,
                {
                    "decision": body.decision,
                    "reason": body.reason.strip(),
                    "version": v + 1,
                    "rule_version": ver,
                },
            )
            self.db.commit()
            return {"decision": body.decision, "version": v + 1, "rule_version": ver}
        except Exception:
            self.db.rollback()
            raise
