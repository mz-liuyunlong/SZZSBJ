"""0100 source-preserving projections. No jobs, external calls or legacy writes."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from app.integrations.lingxing.security import canonical_json, redact_json

from . import sku_ad_foundation_models as models

SKU_FIELDS = {
    "batchGetProductInfo": {
        "bg_customs_export_name": "source_customs_export_name",
        "bg_customs_import_name": "source_customs_import_name",
        "bg_customs_import_price": "source_customs_import_price",
        "bg_export_hs_code": "source_export_hs_code",
        "bg_import_hs_code": "source_import_hs_code",
        "bg_tax_rate": "source_customs_tax_rate",
        "bid": "source_brand_id",
        "brand_name": "source_brand_name",
        "category_full_name": "source_category_path",
        "category_name": "source_category_name",
        "cg_box_height": "source_cg_box_height",
        "cg_box_length": "source_cg_box_length",
        "cg_box_pcs": "source_cg_box_pcs",
        "cg_box_weight": "source_cg_box_weight",
        "cg_box_width": "source_cg_box_width",
        "cg_delivery": "source_purchase_delivery_days",
        "cg_opt_username": "source_purchaser_name",
        "cg_package_height": "source_cg_package_height",
        "cg_package_length": "source_cg_package_length",
        "cg_package_width": "source_cg_package_width",
        "cg_price": "source_purchase_price_amount",
        "cg_product_gross_weight": "source_cg_product_gross_weight",
        "cg_product_height": "source_cg_product_height",
        "cg_product_length": "source_cg_product_length",
        "cg_product_material": "source_purchase_material",
        "cg_product_net_weight": "source_cg_product_net_weight",
        "cg_product_width": "source_cg_product_width",
        "cid": "source_category_id",
        "currency": "source_currency_raw",
        "description": "source_description",
        "is_combo": "source_is_combo_raw",
        "model": "source_model",
        "pic_url": "source_picture_url",
        "product_developer": "source_developer_name",
        "product_developer_uid": "source_developer_uid",
        "product_name": "source_product_name",
        "product_remark": "source_product_remark",
        "purchase_1688_remark": "source_purchase_1688_remark",
        "purchase_remark": "source_purchase_remark",
        "sku": "source_sku_code",
        "sku_identifier": "source_sku_identifier",
        "status": "source_product_status",
        "unit": "source_unit",
    },
    "productList": {
        "bid": "source_brand_id",
        "brand_name": "source_brand_name",
        "category_name": "source_category_name",
        "cg_delivery": "source_purchase_delivery_days",
        "cg_opt_uid": "source_purchaser_uid",
        "cg_opt_username": "source_purchaser_name",
        "cg_price": "source_purchase_price_amount",
        "cg_transport_costs": "source_purchase_transport_amount",
        "cid": "source_category_id",
        "create_time": "source_create_time_raw",
        "is_combo": "source_is_combo_raw",
        "open_status": "source_open_status",
        "pic_url": "source_picture_url",
        "product_developer": "source_developer_name",
        "product_developer_uid": "source_developer_uid",
        "product_name": "source_product_name",
        "product_remark": "source_product_remark",
        "ps_id": "source_spu_id",
        "purchase_1688_remark": "source_purchase_1688_remark",
        "purchase_remark": "source_purchase_remark",
        "sku": "source_sku_code",
        "sku_identifier": "source_sku_identifier",
        "spu": "source_spu_code",
        "status": "source_product_status",
        "status_text": "source_status_text",
        "update_time": "source_update_time_raw",
    },
}
AD_CONFIG_FIELDS = {
    "adGroupName": "ad_group_name",
    "adGroupStatus": "ad_group_status_raw",
    "adName": "ad_name",
    "adStatus": "ad_status_raw",
    "addDate": "add_date_raw",
    "appliedTemplate": "applied_template_json",
    "benchmarkVal": "benchmark_value",
    "bid": "bid_amount",
    "campaignAndTargetingType": "campaign_and_targeting_type",
    "campaignName": "campaign_name",
    "campaignStatus": "campaign_status_raw",
    "campaignType": "campaign_type_raw",
    "entityCreateAt": "entity_created_at_raw",
    "isApplyTime": "is_apply_time_raw",
    "itemImageUrl": "source_image_url",
    "itemPageUrl": "source_item_url",
    "mpAdvertiserName": "source_advertiser_name",
    "mpSellerName": "source_seller_name",
    "reviewReason": "review_reason",
    "reviewStatus": "review_status_raw",
    "suggestedBid": "suggested_bid_amount",
}
AD_METRIC_FIELDS = {
    "aov": "aov_amount",
    "cpa": "cpa_amount",
    "ntbOrderRate": "ntb_order_rate",
    "ntbOrders": "ntb_orders",
    "ntbOrdersPercent": "ntb_orders_percent",
    "ntbRevenue": "ntb_revenue_amount",
    "ntbRevenuePercent": "ntb_revenue_percent",
    "ntbUnits": "ntb_units",
    "ntbUnitsPercent": "ntb_units_percent",
    "otherSkuSales": "other_sku_sales_amount",
    "otherSkuUnits": "other_sku_units",
}


def source_text(value: Any, limit: int | None = None) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    result = str(value).strip()
    if not result or (limit is not None and len(result) > limit):
        return None
    return result


def number(value: Any, precision: int, scale: int) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        v = Decimal(str(value))
        if not v.is_finite() or abs(v) >= Decimal(10) ** (precision - scale):
            return None
        q = v.quantize(Decimal(10) ** -scale)
        return q if q == v else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def integer(value: Any, bits: int = 32) -> int | None:
    v = number(value, 20, 0)
    if v is None or not -(2 ** (bits - 1)) <= v < 2 ** (bits - 1):
        return None
    return int(v)


def epoch_seconds(value: Any) -> datetime | None:
    # ProductList contract: Unix seconds, not milliseconds or local dates.
    v = integer(value, 64)
    if v is None or v <= 0:
        return None
    try:
        return datetime.fromtimestamp(v, UTC)
    except (ValueError, OverflowError, OSError):
        return None


def safe_payload(row: dict) -> dict:
    if not isinstance(row, dict):
        raise ValueError("FOUNDATION_ROW_NOT_OBJECT")
    value = redact_json(row)
    canonical_json(value)  # Reject invalid JSON rather than corrupt a snapshot.
    if not isinstance(value, dict):
        raise ValueError("FOUNDATION_ROW_NOT_OBJECT")
    return value


def typed_fields(table: sa.Table, row: dict, mapping: dict[str, str]) -> dict:
    result = {}
    for key, target in mapping.items():
        col = table.c[target]
        value = row.get(key)
        if isinstance(col.type, sa.Numeric):
            result[target] = number(value, col.type.precision, col.type.scale)
        elif isinstance(col.type, sa.BigInteger):
            result[target] = integer(value, 64)
        elif isinstance(col.type, sa.Integer):
            result[target] = integer(value)
        elif isinstance(col.type, sa.JSON):
            result[target] = value
        else:
            result[target] = source_text(value, getattr(col.type, "length", None))
    return result


def objects(value: Any):
    if isinstance(value, list):
        return ((i, v) for i, v in enumerate(value) if isinstance(v, dict))
    if isinstance(value, dict):
        return iter(((0, value),))
    return iter(())


def project_sku(row: dict, interface: str) -> tuple[dict, list, list, list]:
    if interface not in {"productList", "batchGetProductInfo", "productInfo"}:
        raise ValueError("FOUNDATION_UNKNOWN_SKU_INTERFACE")
    payload = safe_payload(row)
    sku_id = source_text(payload.get("id"), 255)
    if sku_id is None:
        raise ValueError("FOUNDATION_SKU_ID_MISSING")
    snapshot = typed_fields(
        models.LingxingSkuSourceSnapshot_table,
        payload,
        SKU_FIELDS.get(interface, SKU_FIELDS["batchGetProductInfo"]),
    )
    if interface == "productList":
        snapshot.update(
            source_created_at=epoch_seconds(payload.get("create_time")),
            source_updated_at=epoch_seconds(payload.get("update_time")),
        )
    snapshot.update(
        lingxing_sku_id=sku_id,
        payload_json=payload,
        source_payload_hash=hashlib.sha256(canonical_json(payload).encode()).hexdigest(),
    )
    quotes, tiers, countries = [], [], []
    qmap = {
        "psq_id": "source_quote_id",
        "product_id": "source_product_id",
        "supplier_id": "supplier_id",
        "supplier_code": "supplier_code",
        "supplier_name": "supplier_name",
        "is_primary": "is_primary_raw",
        "quote_cg_delivery": "delivery_days",
        "cg_price": "price_amount",
        "cg_currency_icon": "currency_symbol_raw",
        "quote_remark": "quote_remark",
        "supplier_product_url": "supplier_product_urls_json",
    }
    tmap = {
        "currency": "currency_raw",
        "currency_icon": "currency_symbol_raw",
        "is_tax": "is_tax_raw",
        "tax_rate": "tax_rate",
        "moq": "moq",
        "price": "price_amount",
        "price_with_tax": "price_with_tax_amount",
    }
    for ordinal, quote in objects(payload.get("supplier_quote")):
        qid = uuid4()
        quotes.append(
            dict(
                id=qid,
                source_ordinal=ordinal,
                payload_json=quote,
                **typed_fields(models.LingxingSkuSupplierQuoteExtension_table, quote, qmap),
            )
        )
        for ci, currency in objects(quote.get("quotes")):
            for ti, tier in objects(currency.get("step_prices")):
                combined = {
                    k: currency.get(k) for k in ("currency", "currency_icon", "is_tax", "tax_rate")
                }
                combined.update({k: tier.get(k) for k in ("moq", "price", "price_with_tax")})
                tiers.append(
                    dict(
                        id=uuid4(),
                        supplier_quote_id=qid,
                        quote_currency_ordinal=ci,
                        tier_ordinal=ti,
                        payload_json=tier,
                        **typed_fields(
                            models.LingxingSkuSupplierTierExtension_table, combined, tmap
                        ),
                    )
                )
    suffixes = {
        "bg_import_hs_code": "import_hs_code",
        "bg_tax_rate": "tax_rate",
        "cg_transport_costs": "transport_amount",
        "currency": "transport_currency_raw",
        "clearance_price": "clearance_price_amount",
        "clearance_price_currency": "clearance_currency_raw",
    }
    for ordinal, relation in objects(payload.get("product_logistics_relation")):
        prefixes = sorted(
            {
                m.group(1)
                for k in relation
                if (m := re.fullmatch(r"([A-Z]{2})_(.+)", k)) and m.group(2) in suffixes
            }
        )
        for country in prefixes:
            values = {
                key: value for key, value in relation.items() if key.startswith(country + "_")
            }
            cmap = {country + "_" + suffix: field for suffix, field in suffixes.items()}
            countries.append(
                dict(
                    id=uuid4(),
                    relation_ordinal=ordinal,
                    country_code=country,
                    payload_json=values,
                    **typed_fields(models.LingxingSkuCountryLogisticsExtension_table, values, cmap),
                )
            )
    return snapshot, quotes, tiers, countries


def project_ad(row: dict) -> tuple[dict, dict]:
    payload = safe_payload(row)
    keys = {
        "advertiserId": "advertiser_id",
        "campaignId": "campaign_id",
        "adGroupId": "ad_group_id",
        "adItemId": "ad_item_id",
        "itemId": "item_id",
    }
    identity = {target: source_text(payload.get(key), 128) for key, target in keys.items()}
    if not all(identity.values()):
        raise ValueError("FOUNDATION_AD_IDENTITY_INCOMPLETE")
    config = typed_fields(models.WalmartAdItemConfigExtension_table, payload, AD_CONFIG_FIELDS)
    config.update(identity, payload_json=payload, source_key=source_text(payload.get("key")))
    metrics = typed_fields(models.WalmartAdItemDailyExtension_table, payload, AD_METRIC_FIELDS)
    metrics.update(payload_json=payload, advertiser_id=identity["advertiser_id"])
    return config, metrics


def require_observed_at(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("FOUNDATION_OBSERVATION_TIME_UNVERIFIED")


def publish_sku_observation(
    session,
    *,
    account: str,
    identity_id: UUID,
    interface: str,
    raw_request_ref_id: UUID,
    ordinal: int,
    observed_at: datetime,
    row: dict,
) -> str:
    """Called only with a verified RAW membership. Caller owns transaction/savepoint.

    Never updates any existing business table. Serialize only this extension key.
    """
    require_observed_at(observed_at)
    if ordinal < 0 or not source_text(account, 128):
        raise ValueError("FOUNDATION_SKU_SCOPE_INVALID")
    snap, quotes, tiers, countries = project_sku(row, interface)
    identity = session.execute(
        sa.text("""SELECT id FROM dwd_lingxing_sku_identity_index
        WHERE id=:id AND provider='lingxing' AND source_account_ref=:account
          AND lingxing_sku_id=:sku"""),
        dict(id=identity_id, account=account, sku=snap["lingxing_sku_id"]),
    ).scalar_one_or_none()
    if identity is None:
        raise ValueError("FOUNDATION_SKU_IDENTITY_MISMATCH")
    session.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"sku-ad-foundation-v1:{account}:{identity_id}:{interface}"},
    )
    st = models.LingxingSkuSourceSnapshot_table
    ct = models.LingxingSkuSourceCurrent_table
    scope = dict(
        source_account_ref=account, sku_identity_id=identity_id, source_interface=interface
    )
    where = sa.and_(*(ct.c[key] == value for key, value in scope.items()))
    cur = session.execute(sa.select(ct).where(where)).mappings().one_or_none()
    older = bool(cur and observed_at < cur["last_observed_at"])
    # Historical replay must preserve distinct earlier source payloads without
    # replacing the latest pointer. The RAW identity is an idempotent boundary.
    if older:
        already = session.execute(
            sa.select(st.c.id).where(
                st.c.source_account_ref == account,
                st.c.source_interface == interface,
                st.c.source_raw_request_ref_id == raw_request_ref_id,
                st.c.source_item_ordinal == ordinal,
            )
        ).scalar_one_or_none()
        if already is not None:
            return "older_observation"
    if cur:
        previous = session.execute(
            sa.select(st.c.source_payload_hash).where(st.c.id == cur["snapshot_id"])
        ).scalar_one()
        if observed_at == cur["last_observed_at"] and previous != snap["source_payload_hash"]:
            raise ValueError("FOUNDATION_SKU_EQUAL_TIME_CONFLICT")
    else:
        previous = None
    if cur and previous == snap["source_payload_hash"]:
        sid = cur["snapshot_id"]
        result = "unchanged"
    else:
        sid = uuid4()
        values = dict(
            snap,
            **scope,
            id=sid,
            source_raw_request_ref_id=raw_request_ref_id,
            source_item_ordinal=ordinal,
            source_observed_at=observed_at,
            parser_version="sku-ad-foundation-v1",
        )
        session.execute(st.insert().values(**values))
        if quotes:
            session.execute(
                models.LingxingSkuSupplierQuoteExtension_table.insert(),
                [dict(x, snapshot_id=sid) for x in quotes],
            )
        if tiers:
            session.execute(models.LingxingSkuSupplierTierExtension_table.insert(), tiers)
        if countries:
            session.execute(
                models.LingxingSkuCountryLogisticsExtension_table.insert(),
                [dict(x, snapshot_id=sid) for x in countries],
            )
        result = "changed"
    if older:
        return "older_observation"
    pointer = dict(
        scope,
        snapshot_id=sid,
        last_observed_at=observed_at,
        last_raw_request_ref_id=raw_request_ref_id,
        last_item_ordinal=ordinal,
    )
    stmt = insert(ct).values(**pointer)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=list(scope),
            set_={
                **{k: stmt.excluded[k] for k in pointer if k not in scope},
                "updated_at": sa.func.now(),
            },
        )
    )
    return result


def read_development_dates(session, *, account: str, identity_ids: list[UUID]) -> dict:
    """Product management/SKU progress read contract; no fallback to system creation time."""
    if not identity_ids:
        return {}
    if len(identity_ids) > 1000:
        raise ValueError("FOUNDATION_READ_LIMIT")
    st, ct = models.LingxingSkuSourceSnapshot_table, models.LingxingSkuSourceCurrent_table
    query = (
        sa.select(ct.c.sku_identity_id, st.c.source_created_at)
        .join(st, st.c.id == ct.c.snapshot_id)
        .where(
            ct.c.source_account_ref == account,
            ct.c.source_interface == "productList",
            ct.c.sku_identity_id.in_(identity_ids),
        )
    )
    return dict(session.execute(query).all())


def publish_ad_config(
    session, *, account: str, blob_id: UUID, ordinal: int, observed_at: datetime, row: dict
) -> None:
    """Store an observation, not proof that the ad is currently running.

    Caller must supply verified account and blob lineage. No financial fact writes.
    """
    require_observed_at(observed_at)
    if ordinal < 0 or not source_text(account, 128):
        raise ValueError("FOUNDATION_AD_SCOPE_INVALID")
    config, _ = project_ad(row)
    accounts = (
        session.execute(
            sa.text("""SELECT DISTINCT source_account_ref FROM dim_walmart_advertisers
        WHERE advertiser_id=:advertiser"""),
            {"advertiser": config["advertiser_id"]},
        )
        .scalars()
        .all()
    )
    if accounts != [account]:
        raise ValueError("FOUNDATION_AD_ACCOUNT_UNVERIFIED")
    table = models.WalmartAdItemConfigExtension_table
    config.update(
        source_account_ref=account,
        source_blob_id=blob_id,
        source_ordinal=ordinal,
        source_observed_at=observed_at,
    )
    stmt = insert(table).values(**config)
    keys = [c.name for c in table.primary_key]
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=keys,
            set_={
                **{k: stmt.excluded[k] for k in config if k not in keys},
                "updated_at": sa.func.now(),
            },
            where=stmt.excluded.source_observed_at > table.c.source_observed_at,
        )
    )


def publish_ad_daily_extension(
    session,
    *,
    account: str,
    business_date_la,
    source_line_hash: str,
    blob_id: UUID,
    ordinal: int,
    observed_at: datetime,
    row: dict,
    currency_code: str | None = None,
) -> None:
    """Use the exact date/hash of the existing deduplicated fact writer, not blob time.

    Must be invoked with matching source row in the existing writer transaction.
    Historical replay is not safe without exact fact-row provenance.
    """
    require_observed_at(observed_at)
    if ordinal < 0 or not re.fullmatch(r"[0-9a-f]{64}", source_line_hash):
        raise ValueError("FOUNDATION_AD_FACT_KEY_INVALID")
    config, metrics = project_ad(row)
    fact = (
        session.execute(
            sa.text("""SELECT item_id, campaign_id, ad_group_id, ad_item_id,
        ad_spend_currency_code FROM fact_walmart_ad_item_sp_daily
        WHERE business_date_la=:day AND source_account_ref=:account AND advertiser_id=:advertiser
          AND source_line_hash=:hash"""),
            dict(
                day=business_date_la,
                account=account,
                advertiser=config["advertiser_id"],
                hash=source_line_hash,
            ),
        )
        .mappings()
        .one_or_none()
    )
    if fact is None or any(
        fact[k] != config[k] for k in ("item_id", "campaign_id", "ad_group_id", "ad_item_id")
    ):
        raise ValueError("FOUNDATION_AD_FACT_BINDING_UNVERIFIED")
    if currency_code is not None and currency_code != fact["ad_spend_currency_code"]:
        raise ValueError("FOUNDATION_AD_CURRENCY_MISMATCH")
    table = models.WalmartAdItemDailyExtension_table
    metrics.update(
        source_account_ref=account,
        business_date_la=business_date_la,
        source_line_hash=source_line_hash,
        source_blob_id=blob_id,
        source_ordinal=ordinal,
        source_observed_at=observed_at,
        currency_code=fact["ad_spend_currency_code"],
    )
    stmt = insert(table).values(**metrics)
    keys = [c.name for c in table.primary_key]
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=keys,
            set_={
                **{k: stmt.excluded[k] for k in metrics if k not in keys},
                "updated_at": sa.func.now(),
            },
            where=stmt.excluded.source_observed_at > table.c.source_observed_at,
        )
    )


def sku_payload_rows(payload: dict, interface: str) -> list[dict]:
    if not isinstance(payload, dict):
        raise ValueError("FOUNDATION_SKU_PAYLOAD_INVALID")
    data = payload.get("data")
    if interface == "productList" and not isinstance(data, list):
        nested = payload.get("productList")
        data = nested.get("data") if isinstance(nested, dict) else None
    if interface == "productInfo" and isinstance(data, dict):
        data = [data]
    if (
        not isinstance(data, list)
        or len(data) > 1000
        or any(not isinstance(row, dict) for row in data)
    ):
        raise ValueError("FOUNDATION_SKU_PAYLOAD_INVALID")
    ids = [source_text(row.get("id"), 255) for row in data]
    if None in ids or len(set(ids)) != len(ids):
        raise ValueError("FOUNDATION_SKU_MEMBERSHIP_INVALID")
    return data


def publish_sku_raw_page(session, raw_request_ref_id: UUID) -> dict:
    """Process one existing successful SKU RAW page, never fetch an external API.

    ProductList membership verifies the raw ordinal; batch membership verifies ID,
    because request order and returned response order can differ. Caller owns the
    transaction. This service is intentionally not scheduled in this patch.
    """
    evidence = (
        session.execute(
            sa.text("""SELECT r.run_id, r.received_at,
        s.source_account_ref, s.interface_key, b.payload_json
        FROM ods_api_raw_request_refs r JOIN gov_integration_sync_runs s ON s.id=r.run_id
        JOIN ods_api_raw_blobs b ON b.id=r.raw_blob_id
        WHERE r.id=:ref AND r.is_success AND s.provider='lingxing'
          AND s.status='succeeded' AND b.storage_mode='database'"""),
            {"ref": raw_request_ref_id},
        )
        .mappings()
        .one_or_none()
    )
    if evidence is None or evidence["interface_key"] not in ("productList", "batchGetProductInfo"):
        raise ValueError("FOUNDATION_SKU_RAW_REF_UNVERIFIED")
    interface = evidence["interface_key"]
    rows = sku_payload_rows(evidence["payload_json"], interface)
    if interface == "productList":
        query = (
            "SELECT m.lingxing_sku_id, m.source_item_ordinal AS ordinal, i.id AS "
            "identity_id\n"
            "            FROM ods_lingxing_productlist_sku_refs m JOIN "
            "dwd_lingxing_sku_identity_index i\n"
            "              ON i.provider='lingxing' AND "
            "i.source_account_ref=m.source_account_ref AND "
            "i.lingxing_sku_id=m.lingxing_sku_id\n"
            "            WHERE m.raw_request_ref_id=:ref AND m.run_id=:run AND "
            "m.source_account_ref=:account"
        )
    else:
        query = (
            "SELECT m.lingxing_sku_id, NULL AS ordinal, i.id AS identity_id\n"
            "            FROM ods_lingxing_product_info_batch_items m JOIN "
            "dwd_lingxing_sku_identity_index i\n"
            "              ON i.provider='lingxing' AND "
            "i.source_account_ref=m.source_account_ref AND "
            "i.lingxing_sku_id=m.lingxing_sku_id\n"
            "            WHERE m.raw_request_ref_id=:ref AND m.run_id=:run AND "
            "m.source_account_ref=:account\n"
            "              AND m.item_status='succeeded'"
        )
    membership = (
        session.execute(
            sa.text(query),
            {
                "ref": raw_request_ref_id,
                "run": evidence["run_id"],
                "account": evidence["source_account_ref"],
            },
        )
        .mappings()
        .all()
    )
    by_id = {m["lingxing_sku_id"]: m for m in membership}
    if len(by_id) != len(membership) or set(by_id) != {source_text(r.get("id"), 255) for r in rows}:
        raise ValueError("FOUNDATION_SKU_MEMBERSHIP_MISMATCH")
    for ordinal, row in enumerate(rows):
        m = by_id[source_text(row["id"], 255)]
        if interface == "productList" and m["ordinal"] != ordinal:
            raise ValueError("FOUNDATION_SKU_ORDINAL_MISMATCH")
    counts = {"changed": 0, "unchanged": 0, "older_observation": 0}
    # Stable acquisition order reduces extension-only lock conflicts.
    for ordinal, row in sorted(enumerate(rows), key=lambda x: str(x[1]["id"])):
        m = by_id[source_text(row["id"], 255)]
        result = publish_sku_observation(
            session,
            account=evidence["source_account_ref"],
            identity_id=m["identity_id"],
            interface=interface,
            raw_request_ref_id=raw_request_ref_id,
            ordinal=ordinal,
            observed_at=evidence["received_at"],
            row=row,
        )
        counts[result] += 1
    return counts


def ad_payload_rows(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        raise ValueError("FOUNDATION_AD_PAYLOAD_INVALID")
    data = payload.get("data")
    if isinstance(data, dict):
        data = next(
            (data[k] for k in ("list", "rows", "data") if isinstance(data.get(k), list)), None
        )
    if (
        not isinstance(data, list)
        or len(data) > 1000
        or any(not isinstance(row, dict) for row in data)
    ):
        raise ValueError("FOUNDATION_AD_PAYLOAD_INVALID")
    return data


def publish_ad_raw_blob_config(session, blob_id: UUID) -> dict:
    """Process one retained ad report blob; no inference about daily business date."""
    source = (
        session.execute(
            sa.text("""SELECT b.received_at, b.payload_json FROM ods_api_raw_blobs b
        JOIN gov_raw_retention_policies p ON p.id=b.retention_policy_id
        WHERE b.id=:id AND b.storage_mode='database'
          AND p.policy_key='lingxing-data-pages-walmart-ad-item-sp-list-v1'"""),
            {"id": blob_id},
        )
        .mappings()
        .one_or_none()
    )
    if source is None:
        raise ValueError("FOUNDATION_AD_BLOB_UNVERIFIED")
    rows = ad_payload_rows(source["payload_json"])
    counts = {"projected": 0, "incomplete_identity": 0, "unmapped_account": 0}
    for ordinal, row in enumerate(rows):
        try:
            config, _ = project_ad(row)
        except ValueError as exc:
            if str(exc) != "FOUNDATION_AD_IDENTITY_INCOMPLETE":
                raise
            counts["incomplete_identity"] += 1
            continue
        accounts = (
            session.execute(
                sa.text(
                    "SELECT DISTINCT source_account_ref FROM "
                    "dim_walmart_advertisers WHERE advertiser_id=:advertiser"
                ),
                {"advertiser": config["advertiser_id"]},
            )
            .scalars()
            .all()
        )
        if len(accounts) != 1:
            counts["unmapped_account"] += 1
            continue
        publish_ad_config(
            session,
            account=accounts[0],
            blob_id=blob_id,
            ordinal=ordinal,
            observed_at=source["received_at"],
            row=row,
        )
        counts["projected"] += 1
    return counts


def evaluate_listing_ad_status(
    rows: list[dict],
    *,
    coverage_verified: bool,
    account_mapping_verified: bool,
    observed_after: datetime,
    checked_at: datetime,
) -> tuple[bool | None, str]:
    """Conservative candidate rule, NOT wired to production or persisted automatically.

    Caller must supply only records for one exact account/store/item, with account
    status joined. A report's absence is not verified coverage. No spend is used.
    The freshness window and accepted status vocabulary require owner validation.
    """
    require_observed_at(observed_after)
    require_observed_at(checked_at)
    if observed_after > checked_at:
        raise ValueError("FOUNDATION_AD_FRESHNESS_INVALID")
    if not account_mapping_verified:
        return None, "account_mapping_unverified"
    unknown = False
    for row in rows:
        seen = row.get("source_observed_at")
        if (
            not isinstance(seen, datetime)
            or seen.tzinfo is None
            or not observed_after <= seen <= checked_at
        ):
            unknown = True
            continue

        def status(key, row=row):
            value = source_text(row.get(key))
            return value.casefold() if value else None

        account = status("source_account_status_raw")
        campaign = status("campaign_status_raw")
        group = status("ad_group_status_raw")
        ad = status("ad_status_raw")
        review = status("review_status_raw")
        if (
            account == "0"
            or campaign in {"paused", "completed"}
            or group in {"disabled", "delete"}
            or ad in {"disabled", "deleted"}
        ):
            continue
        if (
            account == "1"
            and campaign in {"enabled", "live"}
            and group == "enabled"
            and ad == "enabled"
            and review == "approved"
        ):
            if coverage_verified:
                return True, "enabled_item_verified"
            unknown = True
            continue
        unknown = True
    if not coverage_verified:
        return None, "report_coverage_unverified"
    if unknown:
        return None, "state_or_freshness_unverified"
    return False, "no_enabled_item_in_verified_scope"
