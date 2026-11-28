"""Authenticated product and rule reads/writes. Never call the upstream on page reads."""

from __future__ import annotations

from decimal import Decimal
from html.parser import HTMLParser
from typing import Literal
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.dialects.postgresql import insert

from app.core.config import AppEnvironment, get_database_url, get_settings
from app.db.session import get_session_factory
from app.modules.data_pages.models import WalmartListingDimension
from app.modules.woocommerce_config.models import WooCommerceStore
from app.modules.woocommerce_config.service import WooCommerceConfigError

from .models import (
    biz_woo_publish_brand_rules as brands,
)
from .models import (
    biz_woo_publish_settings as settings,
)
from .models import (
    biz_woo_submission_store_configs as submissions,
)
from .models import (
    dim_woocommerce_products as products,
)
from .models import (
    map_woocommerce_listing as links,
)


def fail(code, status=422):
    raise WooCommerceConfigError(code, status)


class Bullets(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.pieces = []
        self.points = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            if self.depth == 0:
                self.pieces = []
            self.depth += 1

    def handle_data(self, data):
        if self.depth:
            self.pieces.append(data)

    def handle_endtag(self, tag):
        if tag == "li" and self.depth:
            self.depth -= 1
            if not self.depth:
                value = " ".join(" ".join(self.pieces).split())
                if value:
                    self.points.append(value)


def bullets(value):
    parser = Bullets()
    parser.feed(value or "")
    parser.close()
    return parser.points


def read_catalog(
    *,
    page=1,
    page_size=50,
    keyword="",
    search_type="all",
    stores_filter=(),
    brands_filter=(),
    stock_filter=(),
    status="all",
    description_filter=(),
    sort_key="listedAt",
    sort_order="descend",
):
    # All counts, filters, sort and pagination operate on the database, not a 5000-row UI snapshot.
    store = WooCommerceStore.__table__
    wm = WalmartListingDimension.__table__
    identity = sa.and_(
        links.c.source_account_ref == wm.c.source_account_ref,
        links.c.source_store_id == wm.c.store_id,
        links.c.source_item_id == wm.c.item_id,
    )
    base = products.join(store, products.c.store_id == store.c.id)
    conditions = []
    if stores_filter:
        conditions.append(products.c.store_id.in_(stores_filter))
    if stock_filter:
        conditions.append(products.c.stock_status.in_(stock_filter))
    term = keyword.strip()
    if term:
        # Literal substring search, including exact linked Walmart identifiers.
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

        def matches(col):
            return col.ilike(like, escape="\\")

        source_match = sa.exists(
            sa.select(1)
            .select_from(links.join(wm, identity))
            .where(
                links.c.woo_store_id == products.c.store_id,
                links.c.woo_product_id == products.c.woo_product_id,
                sa.or_(matches(links.c.source_item_id), matches(wm.c.store_name)),
            )
        )
        choices = {
            "name": matches(products.c.name),
            "sku": matches(products.c.sku),
            "id": matches(sa.cast(products.c.woo_product_id, sa.Text)),
        }
        conditions.append(choices.get(search_type, sa.or_(*choices.values(), source_match)))
    if brands_filter:
        term_rows = (
            sa.func.jsonb_array_elements(
                sa.func.coalesce(
                    products.c.brands, sa.cast(sa.literal("[]"), products.c.brands.type)
                )
            )
            .table_valued("value")
            .alias("brand_term")
        )
        choices = [
            sa.exists(
                sa.select(1)
                .select_from(term_rows)
                .where(
                    term_rows.c.value.op("->>")("name").in_(
                        [b for b in brands_filter if b != "missing"]
                    )
                )
            )
        ]
        if "missing" in brands_filter:
            choices.append(
                sa.or_(
                    products.c.brands.is_(None), sa.func.jsonb_array_length(products.c.brands) == 0
                )
            )
        conditions.append(sa.or_(*choices))
    # Match the rendered five-point count: actual nonempty list items are derived from HTML,
    # never from the long description. Use the same parser for description-specific filtering.
    statuses = ("publish", "draft", "pending", "private")

    def status_condition(value):
        if value == "other":
            return sa.or_(
                products.c.publish_status.is_(None), products.c.publish_status.not_in(statuses)
            )
        return products.c.publish_status == value

    with get_session_factory()() as session:
        session.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        if description_filter and set(description_filter) != {"complete", "unconfirmed"}:
            accepted = []
            for r in session.execute(
                sa.select(products.c.id, products.c.short_description)
                .select_from(base)
                .where(*conditions)
            ):
                if (
                    "complete" if len(bullets(r.short_description)) == 5 else "unconfirmed"
                ) in description_filter:
                    accepted.append(r.id)
            conditions.append(products.c.id.in_(accepted))
        stats = session.execute(
            sa.select(products.c.publish_status, sa.func.count())
            .select_from(base)
            .where(*conditions)
            .group_by(products.c.publish_status)
        ).all()
        summary = {k: 0 for k in (*statuses, "other", "all")}
        for st, count in stats:
            summary[st if st in statuses else "other"] += count
            summary["all"] += count
        filters = conditions + ([] if status == "all" else [status_condition(status)])
        total = session.execute(
            sa.select(sa.func.count()).select_from(base).where(*filters)
        ).scalar_one()
        sort = {
            "name": products.c.name,
            "store": store.c.name,
            "images": sa.func.jsonb_array_length(products.c.image_urls),
            "sku": products.c.sku,
            "stock": products.c.stock_quantity,
            "price": products.c.price,
            "brand": sa.cast(products.c.brands, sa.Text),
            "listedAt": products.c.published_at,
            "status": products.c.publish_status,
        }.get(sort_key, products.c.source_created_at)
        ordering = (sort.asc() if sort_order == "ascend" else sort.desc()).nulls_last()
        fields = [c for c in products.c if c.name not in {"raw_id"}]
        rows = (
            session.execute(
                sa.select(*fields, store.c.name.label("store_name"))
                .select_from(base)
                .where(*filters)
                .order_by(
                    ordering,
                    products.c.source_created_at.desc().nulls_last(),
                    products.c.store_id,
                    products.c.woo_product_id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .mappings()
            .all()
        )
        ids = [(r["store_id"], r["woo_product_id"]) for r in rows]
        linked = (
            session.execute(
                sa.select(
                    links.c.woo_store_id,
                    links.c.woo_product_id,
                    links.c.source_account_ref,
                    links.c.source_store_id,
                    links.c.source_item_id,
                    wm.c.store_name,
                )
                .select_from(links.join(wm, identity))
                .where(sa.tuple_(links.c.woo_store_id, links.c.woo_product_id).in_(ids))
                .order_by(
                    links.c.source_account_ref, links.c.source_store_id, links.c.source_item_id
                )
            )
            .mappings()
            .all()
            if ids
            else []
        )
        stores = [
            dict(value=str(r.id), label=r.name)
            for r in session.execute(sa.select(store.c.id, store.c.name).order_by(store.c.name))
        ]
        terms = (
            sa.func.jsonb_array_elements(
                sa.func.coalesce(
                    products.c.brands, sa.cast(sa.literal("[]"), products.c.brands.type)
                )
            )
            .table_valued("value")
            .alias("term")
        )
        brand_name = terms.c.value.op("->>")("name")
        brand_options = [
            r
            for r in session.scalars(
                sa.select(brand_name)
                .select_from(products.join(terms, sa.true()))
                .where(brand_name.is_not(None), brand_name != "")
                .distinct()
                .order_by(brand_name)
            )
        ]
    grouped = {}
    for row in linked:
        grouped.setdefault((row["woo_store_id"], row["woo_product_id"]), []).append(
            {
                "account": row["source_account_ref"],
                "storeId": row["source_store_id"],
                "itemId": row["source_item_id"],
                "storeName": row["store_name"] or row["source_store_id"],
                "url": "https://www.walmart.com/ip/" + row["source_item_id"]
                if row["source_item_id"].isascii() and row["source_item_id"].isdigit()
                else "",
            }
        )
    result = []
    for row in rows:
        images = row["image_urls"] or []
        result.append(
            dict(
                id=str(row["woo_product_id"]),
                storeId=str(row["store_id"]),
                store=row["store_name"],
                name=row["name"],
                sku=row["sku"] or "",
                brands=[x["name"] for x in (row["brands"] or []) if x.get("name")],
                images=len(images),
                imageUrl=images[0] if images else None,
                points=bullets(row["short_description"]),
                descriptionLength=len(row["description"] or ""),
                stockStatus=row["stock_status"] or "unknown",
                stockQuantity=row["stock_quantity"],
                price=str(row["price"]) if row["price"] is not None else "",
                regularPrice="",
                currency=row["currency_code"],
                createdAt=row["source_created_at"].isoformat() if row["source_created_at"] else "",
                listedAt=row["published_at"].isoformat() if row["published_at"] else None,
                status=row["publish_status"] or "unknown",
                url=row["permalink"] or "",
                lastSyncedAt=row["last_synced_at"].isoformat(),
                sources=grouped.get((row["store_id"], row["woo_product_id"]), []),
            )
        )
    return {
        "items": result,
        "total": total,
        "summary": summary,
        "stores": stores,
        "brands": brand_options,
    }


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BrandRule(Strict):
    source_brand: str = Field(min_length=1, max_length=255)
    target_store_id: UUID
    target_brand_id: str = Field(min_length=1, max_length=128)
    target_category_id: str = Field(min_length=1, max_length=128)
    enabled: bool = False


class SubmissionRule(Strict):
    source_account_ref: str = Field(min_length=1, max_length=128)
    source_store_id: str = Field(min_length=1, max_length=128)
    submission_store_id: str = Field(min_length=1, max_length=128)


class RuleWrite(Strict):
    version: int = Field(ge=0)
    # Desired configuration only. No worker reads this flag in this release.
    auto_publish_enabled: bool = False
    listing_status: Literal["active", "review"] = "active"
    price_mode: Literal["original", "fixed", "percent"] = "fixed"
    price_markup: Decimal = Field(default=Decimal("2"), ge=0, max_digits=18, decimal_places=4)
    stock_quantity: int | None = Field(default=None, ge=0, le=2147483647)
    retry_enabled: bool = False
    retry_limit: int = Field(default=3, ge=0, le=20)
    submission_interval_days: int = Field(default=60, ge=1, le=3650)
    mappings: list[BrandRule] = Field(max_length=500)
    submission_stores: list[SubmissionRule] = Field(max_length=500)


CONFIG_FIELDS = (
    "auto_publish_enabled",
    "listing_status",
    "price_mode",
    "price_markup",
    "stock_quantity",
    "retry_enabled",
    "retry_limit",
    "submission_interval_days",
)


def option_data(session):
    store = WooCommerceStore.__table__
    store_rows = (
        session.execute(
            sa.select(store.c.id, store.c.name, store.c.store_url).order_by(store.c.name)
        )
        .mappings()
        .all()
    )
    shops = {
        str(row["id"]): dict(
            value=str(row["id"]),
            label=row["name"] + " · " + row["store_url"],
            brands={},
            categories={},
        )
        for row in store_rows
    }
    for row in session.execute(
        sa.select(products.c.store_id, products.c.brands, products.c.categories).distinct()
    ).mappings():
        target = shops.get(str(row["store_id"]))
        if target is None:
            continue
        for field in ("brands", "categories"):
            for term in row[field] or []:
                if term.get("id") is not None:
                    target[field][str(term["id"])] = str(term.get("name") or term["id"])
    for target in shops.values():
        for field in ("brands", "categories"):
            target[field] = [
                dict(value=k, label=v + " (" + k + ")") for k, v in sorted(target[field].items())
            ]
    wm = WalmartListingDimension.__table__
    wm_rows = (
        session.execute(
            sa.select(
                wm.c.source_account_ref,
                wm.c.store_id,
                sa.func.max(wm.c.store_name).label("store_name"),
            )
            .group_by(wm.c.source_account_ref, wm.c.store_id)
            .order_by(wm.c.source_account_ref, wm.c.store_id)
        )
        .mappings()
        .all()
    )
    walmart_stores = [
        dict(
            account=row["source_account_ref"],
            storeId=row["store_id"],
            label=(row["store_name"] or row["store_id"]) + " · " + row["source_account_ref"],
        )
        for row in wm_rows
    ]
    return list(shops.values()), walmart_stores


def read_rules_in_session(session):
    active = (
        session.execute(sa.select(settings).where(settings.c.is_current)).mappings().one_or_none()
    )
    defaults = RuleWrite(version=0, mappings=[], submission_stores=[]).model_dump(mode="json")
    if active:
        defaults.update(
            {k: str(active[k]) if k == "price_markup" else active[k] for k in CONFIG_FIELDS}
        )
        defaults["version"] = active["rule_version"]
    defaults["mappings"] = [
        dict(
            source_brand=r["source_brand"],
            target_store_id=str(r["target_store_id"]),
            target_brand_id=r["target_brand_id"],
            target_category_id=r["target_category_id"],
            enabled=r["enabled"],
        )
        for r in session.execute(
            sa.select(brands).where(brands.c.is_current).order_by(brands.c.normalized_brand)
        ).mappings()
    ]
    defaults["submission_stores"] = [
        dict(
            source_account_ref=r["source_account_ref"],
            source_store_id=r["source_store_id"],
            submission_store_id=r["submission_store_id"],
        )
        for r in session.execute(
            sa.select(submissions).order_by(
                submissions.c.source_account_ref, submissions.c.source_store_id
            )
        ).mappings()
    ]
    stores, wm_stores = option_data(session)
    return {"rules": defaults, "stores": stores, "walmart_stores": wm_stores}


def read_rules():
    with get_session_factory()() as session:
        # Multiple reads must observe a consistent rule version and option set.
        session.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        return read_rules_in_session(session)


def save_rules(payload: RuleWrite, *, actor: str):
    cfg = get_settings()
    url = get_database_url(cfg)
    if cfg.app_env is AppEnvironment.LOCAL and (
        url.host not in ("localhost", "127.0.0.1", "::1") or url.port != 55433 or url.query
    ):
        fail("WOO_RULES_LOCAL_WRITE_BLOCKED", 403)
    normalized = [r.source_brand.strip().casefold() for r in payload.mappings]
    identities = [(r.source_account_ref, r.source_store_id) for r in payload.submission_stores]
    if len(set(normalized)) != len(normalized) or len(set(identities)) != len(identities):
        fail("WOO_DUPLICATE_RULE")
    if payload.auto_publish_enabled and (
        payload.stock_quantity is None or not any(r.enabled for r in payload.mappings)
    ):
        fail("WOO_RULE_INCOMPLETE")
    with get_session_factory()() as session:
        session.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended('woo-publish-rules', 0))")
        )
        old = read_rules_in_session(session)
        if old["rules"]["version"] != payload.version:
            fail("WOO_RULE_VERSION_CONFLICT", 409)
        shop_options = {s["value"]: s for s in old["stores"]}
        source_options = {(s["account"], s["storeId"]) for s in old["walmart_stores"]}
        for r in payload.mappings:
            shop = shop_options.get(str(r.target_store_id))
            if (
                not shop
                or r.target_brand_id not in {x["value"] for x in shop["brands"]}
                or r.target_category_id not in {x["value"] for x in shop["categories"]}
            ):
                fail("WOO_BRAND_CATEGORY_NOT_OBSERVED")
        if any(pair not in source_options for pair in identities):
            fail("WOO_WALMART_STORE_UNKNOWN")
        new_version = payload.version + 1
        session.execute(settings.update().where(settings.c.is_current).values(is_current=False))
        session.execute(
            settings.insert().values(
                id=uuid4(),
                rule_version=new_version,
                is_current=True,
                currency_code="USD",
                updated_by=actor,
                **{key: getattr(payload, key) for key in CONFIG_FIELDS},
            )
        )
        session.execute(brands.update().where(brands.c.is_current).values(is_current=False))
        for rule, norm in zip(payload.mappings, normalized, strict=True):
            session.execute(
                brands.insert().values(
                    id=uuid4(),
                    normalized_brand=norm,
                    rule_version=new_version,
                    is_current=True,
                    updated_by=actor,
                    **rule.model_dump(),
                )
            )
        # Submission configuration is a current-state table; its changes are captured
        # by the versioned settings transaction and the existing config audit log.
        for row in old["rules"]["submission_stores"]:
            pair = (row["source_account_ref"], row["source_store_id"])
            if pair not in identities:
                session.execute(
                    submissions.delete().where(
                        submissions.c.source_account_ref == pair[0],
                        submissions.c.source_store_id == pair[1],
                    )
                )
        for rule in payload.submission_stores:
            statement = insert(submissions).values(
                id=uuid4(), updated_by=actor, **rule.model_dump()
            )
            session.execute(
                statement.on_conflict_do_update(
                    constraint="uq_woo_submission_store",
                    set_=dict(
                        submission_store_id=statement.excluded.submission_store_id,
                        updated_by=actor,
                        updated_at=sa.func.now(),
                    ),
                )
            )
        session.execute(
            sa.text(
                "INSERT INTO biz_config_audit (id, actor, action, object_id) "
                "VALUES (:id, :actor, 'woocommerce.rules.save', :object_id)"
            ),
            dict(id=uuid4(), actor=actor, object_id=f"woo-rules:{new_version}"),
        )
        result = read_rules_in_session(session)
        session.commit()
        return result


class ListingIdentity(Strict):
    source_account_ref: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    item_id: str = Field(min_length=1, max_length=128)


class ListingLookup(Strict):
    identities: list[ListingIdentity] = Field(max_length=500)


def lookup_listing_links(session, identities):
    """Batch exact, previously confirmed associations. No SKU fallback or creation."""
    keys = list(dict.fromkeys((i.source_account_ref, i.store_id, i.item_id) for i in identities))
    if not keys:
        return []
    store = WooCommerceStore.__table__
    exact = sa.tuple_(links.c.source_account_ref, links.c.source_store_id, links.c.source_item_id)
    query = (
        sa.select(
            links.c.source_account_ref,
            links.c.source_store_id,
            links.c.source_item_id,
            products.c.woo_product_id,
            products.c.permalink,
            products.c.price,
            products.c.currency_code,
            products.c.publish_status,
            products.c.stock_status,
            products.c.last_synced_at,
            store.c.name.label("store_name"),
        )
        .select_from(
            links.join(
                products,
                sa.and_(
                    links.c.woo_store_id == products.c.store_id,
                    links.c.woo_product_id == products.c.woo_product_id,
                ),
            ).join(store, products.c.store_id == store.c.id)
        )
        .where(exact.in_(keys))
        .order_by(
            links.c.source_account_ref,
            links.c.source_store_id,
            links.c.source_item_id,
            store.c.name,
            products.c.woo_product_id,
        )
    )
    return [
        dict(
            source_account_ref=r.source_account_ref,
            store_id=r.source_store_id,
            item_id=r.source_item_id,
            woo_product_id=str(r.woo_product_id),
            store_name=r.store_name,
            url=r.permalink,
            price=str(r.price) if r.price is not None else None,
            currency=r.currency_code,
            publish_status=r.publish_status,
            stock_status=r.stock_status,
            last_synced_at=r.last_synced_at.isoformat(),
        )
        for r in session.execute(query)
    ]


def read_listing_links(payload: ListingLookup):
    with get_session_factory()() as session:
        return lookup_listing_links(session, payload.identities)


def read_sync_stores():
    store = WooCommerceStore.__table__
    with get_session_factory()() as session:
        return [
            {"value": "woo:" + str(r.id), "label": r.name}
            for r in session.execute(sa.select(store.c.id, store.c.name).order_by(store.c.name))
        ]
