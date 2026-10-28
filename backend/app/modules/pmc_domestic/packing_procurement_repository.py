"""Bounded read projection over synchronized purchase evidence; no provider calls or writes."""

from collections import defaultdict
from fractions import Fraction

from sqlalchemy import select

from app.modules.integration_sync.models import IntegrationSyncRun
from app.modules.pmc_domestic.packing_suggestions import arrival_metrics
from app.modules.pmc_purchase.dwd_builder import latest_versions
from app.modules.pmc_purchase.models import LingxingPurchaseOrderItemOds as Item
from app.modules.pmc_purchase.models import LingxingPurchasePlanOds as Plan
from app.modules.pmc_purchase.remark_item_ids import extract_remark_item_ids
from app.modules.sku_detail.models import LingxingSkuProductInfoCurrent as Product


class PackingProcurementRepository:
    def __init__(self, session, accounts, skus, lines):
        self.lines = lines
        self.by_key = defaultdict(dict)
        self.plan_totals = defaultdict(int)
        for line in lines:
            self.by_key[(line.source_account_ref, line.order_sn, line.sku)][line.order_item_id] = (
                line.quantity_real
            )
            if line.plan_sn:
                self.plan_totals[(line.source_account_ref, line.plan_sn)] += line.quantity_allocated
        succeeded = select(IntegrationSyncRun.id).where(IntegrationSyncRun.status == "succeeded")
        orders = {line.order_sn for line in lines}
        items = (
            list(
                session.scalars(
                    select(Item).where(
                        Item.source_account_ref.in_(accounts),
                        Item.order_sn.in_(orders),
                        Item.run_id.in_(succeeded),
                    )
                )
            )
            if orders
            else []
        )
        self.items, _ = latest_versions(items, lambda r: (r.order_sn, r.item_id))
        plans = {line.plan_sn for line in lines if line.plan_sn}
        rows = (
            list(
                session.scalars(
                    select(Plan).where(
                        Plan.source_account_ref.in_(accounts),
                        Plan.plan_sn.in_(plans),
                        Plan.run_id.in_(succeeded),
                    )
                )
            )
            if plans
            else []
        )
        self.plans, _ = latest_versions(rows, lambda r: r.plan_sn)
        self.boxes = defaultdict(list)
        for product in (
            session.scalars(
                select(Product).where(
                    Product.source_account_ref.in_(accounts),
                    Product.lingxing_sku_code.in_(skus),
                )
            )
            if skus
            else []
        ):
            self.boxes[(product.source_account_ref, product.lingxing_sku_code)].append(product)

    def arrival(self, account, sku, order_sns):
        unique_sns = sorted(set(order_sns))
        rows = [
            (sn, item, value)
            for sn in unique_sns
            for item, value in self.by_key.get((account, sn, sku), {}).items()
        ]
        complete = bool(rows) and all(self.by_key.get((account, sn, sku)) for sn in unique_sns)
        quantities = [value for _, _, value in rows]
        purchased = (
            sum(quantities)
            if complete and all(type(q) is int and q >= 0 for q in quantities)
            else None
        )
        received = []
        outstanding = []
        refs = []
        for sn, ident, _ in rows:
            row = self.items.get((account, (sn, ident)))
            valid = (
                row is not None
                and row.sku == sku
                and row.is_delete != 1
                and row.quantity_real == self.by_key[(account, sn, sku)][ident]
            )
            # The existing parser retains raw_line in payload_json; quantity_entry
            # has no physical ODS column. Do not confuse the similarly named
            # quantity_receive (outstanding) with goods already received.
            payload = row.payload_json if valid and isinstance(row.payload_json, dict) else {}
            received.append(payload.get("quantity_entry"))
            outstanding.append(row.quantity_receive if valid else None)
            if valid:
                refs.append(str(row.id))
        return {
            "arrival_purchased": purchased,
            **arrival_metrics(
                purchased, received if complete else [], outstanding if complete else []
            ),
            "arrival_source_refs": sorted(refs),
        }

    def weights(self, account, sku, store, order_sns, identities, store_listing_ids):
        selected = [
            r
            for r in self.lines
            if r.source_account_ref == account
            and r.sku == sku
            and r.order_sn in order_sns
            and r.store_id == store
        ]
        weights = defaultdict(Fraction)
        refs = []
        for line in selected:
            plan = self.plans.get((account, line.plan_sn))
            if (
                plan is None
                or plan.sku != sku
                or str(plan.sid) != store
                or plan.is_aux == 1
                or plan.is_combo == 1
                or type(plan.quantity_plan) is not int
                or plan.quantity_plan <= 0
            ):
                return {}, []
            payload = plan.payload_json if isinstance(plan.payload_json, dict) else {}
            found = (
                set(
                    extract_remark_item_ids(
                        [
                            plan.remark,
                            plan.plan_remark,
                            payload.get("item_purchase_remark"),
                        ]
                    )
                )
                & store_listing_ids
            )
            if not found and len(store_listing_ids) == 1:
                found = set(store_listing_ids)
            if len(found) != 1 or not found <= identities:
                return {}, []
            denominator = self.plan_totals[(account, line.plan_sn)]
            if denominator <= 0 or line.quantity_allocated <= 0:
                return {}, []
            item_id = next(iter(found))
            weights[item_id] += Fraction(plan.quantity_plan * line.quantity_allocated, denominator)
            refs.append(str(plan.id))
        return (dict(weights), sorted(set(refs))) if set(weights) == identities else ({}, [])

    def box(self, account, sku):
        rows = self.boxes.get((account, sku), [])
        if len(rows) != 1 or type(rows[0].box_pcs) is not int or rows[0].box_pcs <= 0:
            return None, None
        return rows[0].box_pcs, str(rows[0].source_snapshot_id)
