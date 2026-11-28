"""Read-only upstream catalog ingestion. No publish/submit operation exists here."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from time import monotonic
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_session_factory
from app.modules.woocommerce_config import repository
from app.modules.woocommerce_config.client import (
    ProbeFailure,
    _PinnedHTTPSConnection,
    _resolve_public_ips,
    _status_code,
)
from app.modules.woocommerce_config.schemas import normalize_store_url
from app.modules.woocommerce_config.service import WooCommerceConfigError, _decrypt

from .models import dim_woocommerce_products as products
from .models import raw_woocommerce_products as raw

MAX_PRODUCTS = 5000
PAGE_SIZE = 20
MAX_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 180


def fail(code: str, status: int = 422):
    raise WooCommerceConfigError(code, status)


def request_json(host: str, addresses: list[str], key: str, secret: str, path: str):
    encoded = base64.b64encode(f"{key}:{secret}".encode()).decode()
    for addr in addresses[:2]:
        conn = _PinnedHTTPSConnection(host, addr)
        try:
            conn.request(
                "GET",
                path,
                headers={
                    "Authorization": f"Basic {encoded}",
                    "Accept": "application/json",
                    "User-Agent": "SZZSBJ-WooCommerce-Connector/1.0",
                },
            )
            response = conn.getresponse()
            if response.status != 200:
                fail(_status_code(response.status), 502)
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                fail("WOO_RESPONSE_TOO_LARGE", 502)
            value = json.loads(body.decode("utf-8"))
            serialized = json.dumps(value, allow_nan=False, ensure_ascii=False)
            if any(s and s in serialized for s in (key, secret, encoded)):
                fail("WOO_RESPONSE_CONTAINS_CREDENTIAL", 502)
            return value, response.getheader("X-WP-Total"), response.getheader("X-WP-TotalPages")
        except (OSError, TimeoutError, http.client.HTTPException):
            continue
        except (ValueError, UnicodeError, RecursionError):
            fail("WOO_RESPONSE_INVALID", 502)
        finally:
            conn.close()
    fail("WOO_CONNECTION_FAILED", 502)


def parse_count(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}", value):
        fail("WOO_PAGINATION_HEADERS_INVALID", 502)
    return int(value)


def fetch_catalog(
    store_url, key, secret, *, modified_after=None, modified_before=None, heartbeat=lambda: None
):
    if normalize_store_url(store_url) != store_url:
        fail("WOO_STORE_URL_INVALID")
    host = urlsplit(store_url).hostname
    try:
        addresses = _resolve_public_ips(host)
    except ProbeFailure as exc:
        fail(exc.code, 502)
    started = monotonic()
    heartbeat()
    currency_payload, _, _ = request_json(
        host, addresses, key, secret, "/wp-json/wc/v3/settings/general/woocommerce_currency"
    )
    currency = currency_payload.get("value") if isinstance(currency_payload, dict) else None
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        fail("WOO_CURRENCY_UNVERIFIED", 502)
    seen = set()
    result = []
    expected = None
    page = 1
    while True:
        heartbeat()
        if monotonic() - started > MAX_SECONDS:
            fail("WOO_SYNC_TIME_LIMIT", 502)
        params = {
            "page": page,
            "per_page": PAGE_SIZE,
            "orderby": "id",
            "order": "asc",
            "status": "any",
        }
        if modified_after is not None:
            params.update(
                modified_after=modified_after.isoformat(),
                modified_before=modified_before.isoformat(),
                dates_are_gmt="true",
            )
        query = urlencode(params)
        payload, total_header, pages_header = request_json(
            host, addresses, key, secret, "/wp-json/wc/v3/products?" + query
        )
        total, pages = parse_count(total_header), parse_count(pages_header)
        if total > MAX_PRODUCTS or pages != (total + PAGE_SIZE - 1) // PAGE_SIZE:
            fail("WOO_CATALOG_SIZE_OR_PAGE_INVALID", 502)
        if expected is None:
            expected = (total, pages)
        if expected != (total, pages) or not isinstance(payload, list):
            fail("WOO_CATALOG_CHANGED_DURING_SYNC", 502)
        if len(payload) != min(PAGE_SIZE, max(0, total - (page - 1) * PAGE_SIZE)):
            fail("WOO_PAGE_COUNT_MISMATCH", 502)
        for item in payload:
            if (
                not isinstance(item, dict)
                or type(item.get("id")) is not int
                or item["id"] <= 0
                or item["id"] in seen
            ):
                fail("WOO_PRODUCT_ID_INVALID_OR_DUPLICATE", 502)
            seen.add(item["id"])
            normalized = normalize_product(item, currency)
            if modified_after is not None:
                stamp = normalized[1]["source_modified_at"]
                if stamp is None or not modified_after <= stamp <= modified_before:
                    fail("WOO_INCREMENTAL_WINDOW_NOT_HONORED", 502)
            result.append(normalized)
        if page >= pages:
            break
        page += 1
    if len(result) != expected[0]:
        fail("WOO_CATALOG_COUNT_MISMATCH", 502)
    return currency, result


def str_field(value, max_length=None):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or "\x00" in value or (max_length and len(value) > max_length):
        fail("WOO_PRODUCT_FIELD_INVALID", 502)
    return value


def http_url(value):
    value = str_field(value)
    if not value:
        return None
    try:
        url = urlsplit(value)
        if (
            url.scheme in ("https", "http")
            and url.hostname
            and not url.username
            and not url.password
        ):
            return value
    except ValueError:
        pass
    return None


def utc_value(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    except (ValueError, TypeError, AttributeError):
        fail("WOO_PRODUCT_TIMESTAMP_INVALID", 502)


def money(value):
    if value is None or value == "":
        return None
    try:
        v = Decimal(str(value))
        if (
            not v.is_finite()
            or v < 0
            or v >= Decimal("100000000000000")
            or v != v.quantize(Decimal("0.0001"))
        ):
            raise ValueError
        return v
    except (ValueError, InvalidOperation):
        fail("WOO_PRODUCT_PRICE_INVALID", 502)


def term_list(value):
    if value is None:
        return []
    if not isinstance(value, list):
        fail("WOO_TERMS_INVALID", 502)
    result = []
    for row in value:
        if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] <= 0:
            fail("WOO_TERMS_INVALID", 502)
        result.append(
            {
                "id": row["id"],
                "name": str_field(row.get("name")) or "",
                "slug": str_field(row.get("slug")) or "",
            }
        )
    return result


def normalize_product(item, currency):
    # Intentionally omit arbitrary plugin metadata, password, _links, and extensions.
    # Preserve an auditable approved field set, not an unfiltered credential-bearing response.
    name = str_field(item.get("name"))
    if not name or not name.strip():
        fail("WOO_PRODUCT_NAME_MISSING", 502)
    images = item.get("images") or []
    if not isinstance(images, list) or any(not isinstance(x, dict) for x in images):
        fail("WOO_IMAGES_INVALID", 502)
    image_records = [
        {
            "id": x.get("id") if type(x.get("id")) is int else None,
            "src": http_url(x.get("src")),
            "alt": str_field(x.get("alt")),
        }
        for x in images
    ]
    qty = item.get("stock_quantity")
    if qty is not None and (type(qty) is not int or qty < 0):
        fail("WOO_STOCK_INVALID", 502)
    manage = item.get("manage_stock")
    if manage is not None and type(manage) is not bool:
        fail("WOO_STOCK_INVALID", 502)
    price = money(item.get("price"))
    brands, categories = term_list(item.get("brands")), term_list(item.get("categories"))
    fields = (
        "id",
        "name",
        "sku",
        "type",
        "status",
        "price",
        "regular_price",
        "sale_price",
        "date_created_gmt",
        "date_modified_gmt",
        "date_created",
        "date_modified",
        "manage_stock",
        "stock_quantity",
        "stock_status",
        "short_description",
        "description",
        "catalog_visibility",
        "purchasable",
    )
    evidence = {k: item[k] for k in fields if k in item}
    # Raw fields above are scalar; reject unexpected objects to avoid arbitrary plugin payloads.
    if any(isinstance(v, (dict, list)) for v in evidence.values()):
        fail("WOO_PRODUCT_FIELD_INVALID", 502)
    permalink = http_url(item.get("permalink"))
    evidence.update(
        images=image_records,
        brands=brands,
        categories=categories,
        permalink=permalink,
        currency_code=currency,
    )
    values = dict(
        woo_product_id=item["id"],
        name=name,
        sku=str_field(item.get("sku")),
        permalink=permalink,
        image_urls=[x["src"] for x in image_records if x["src"]],
        short_description=str_field(item.get("short_description")),
        description=str_field(item.get("description")),
        brands=brands,
        categories=categories,
        price=price,
        currency_code=currency,
        manage_stock=manage,
        stock_quantity=qty,
        stock_status=str_field(item.get("stock_status"), 32),
        publish_status=str_field(item.get("status"), 32),
        source_created_at=utc_value(item.get("date_created_gmt")),
        source_modified_at=utc_value(item.get("date_modified_gmt")),
    )
    # The API creation date is not necessarily the first publication date.
    return evidence, values


def sync_store(
    store_id: UUID,
    *,
    actor: str,
    run_id=None,
    window_start=None,
    window_end=None,
    heartbeat=lambda: None,
    finalize=lambda session, result: None,
):
    """Complete bounded full scan, then one transaction per store; never delete on absence."""
    with get_session_factory()() as session:
        # Transaction advisory lock prevents overlapping scans for this store.
        lock = session.execute(
            sa.text("SELECT pg_try_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": "woo-catalog:" + str(store_id)},
        ).scalar_one()
        if not lock:
            fail("WOO_SYNC_ALREADY_RUNNING", 409)
        cfg = repository.get_store(session, store_id)
        if not cfg or not cfg["enabled"] or cfg["last_test_ok"] is not True:
            fail("WOO_STORE_NOT_ENABLED_AND_VERIFIED", 409)
        original = tuple(
            cfg[k] for k in ("store_url", "consumer_key_ciphertext", "consumer_secret_ciphertext")
        )
        currency, catalog = fetch_catalog(
            original[0],
            _decrypt(original[1]),
            _decrypt(original[2]),
            modified_after=window_start,
            modified_before=window_end,
            heartbeat=heartbeat,
        )
        if (
            window_start is not None
            and session.execute(
                sa.select(sa.func.count())
                .select_from(products)
                .where(products.c.store_id == store_id, products.c.currency_code != currency)
            ).scalar_one()
        ):
            fail("WOO_CURRENCY_CHANGED_FULL_SYNC_REQUIRED", 409)
        latest = repository.get_store(session, store_id, for_update=True)
        if (
            not latest
            or not latest["enabled"]
            or latest["last_test_ok"] is not True
            or tuple(
                latest[k]
                for k in ("store_url", "consumer_key_ciphertext", "consumer_secret_ciphertext")
            )
            != original
        ):
            fail("WOO_STORE_CHANGED_DURING_SYNC", 409)
        run_id = str(run_id or uuid4())
        now = datetime.now(UTC)
        changed = 0
        written = 0
        for index, (evidence, values) in enumerate(catalog):
            if index % 100 == 0:
                heartbeat()
            item_id = values["woo_product_id"]
            digest = hashlib.sha256(
                json.dumps(
                    evidence,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest()
            previous = session.execute(
                sa.select(raw.c.id, raw.c.payload_hash)
                .join(products, products.c.raw_id == raw.c.id)
                .where(products.c.store_id == store_id, products.c.woo_product_id == item_id)
            ).first()
            if previous and previous.payload_hash == digest:
                raw_id = previous.id
            else:
                raw_id = uuid4()
                session.execute(
                    raw.insert().values(
                        id=raw_id,
                        store_id=store_id,
                        woo_product_id=item_id,
                        sync_run_id=run_id,
                        payload_hash=digest,
                        raw_payload=evidence,
                        source_modified_at=values["source_modified_at"],
                        fetched_at=now,
                    )
                )
                changed += 1
            data = dict(values, store_id=store_id, raw_id=raw_id, last_synced_at=now)
            statement = insert(products).values(id=uuid4(), **data)
            write_result = session.execute(
                statement.on_conflict_do_update(
                    constraint="uq_woo_dim_product",
                    set_={
                        k: statement.excluded[k]
                        for k in data
                        if k not in ("store_id", "woo_product_id")
                    },
                    where=sa.or_(
                        products.c.source_modified_at.is_(None),
                        statement.excluded.source_modified_at >= products.c.source_modified_at,
                    ),
                )
            )
            written += max(0, write_result.rowcount or 0)
        if window_start is None:
            observed_ids = [values["woo_product_id"] for _, values in catalog]
            # A completed full scan is authoritative for absence; retain the row and evidence.
            missing = session.execute(
                products.update()
                .where(
                    products.c.store_id == store_id,
                    products.c.woo_product_id.not_in(observed_ids),
                    sa.or_(
                        products.c.publish_status.is_(None), products.c.publish_status != "missing"
                    ),
                )
                .values(publish_status="missing")
            )
            written += max(0, missing.rowcount or 0)
        heartbeat()
        repository.add_audit(
            session, actor=actor, action="woocommerce.products.sync", store_id=store_id
        )
        result = {
            "store_id": str(store_id),
            "run_id": run_id,
            "currency": currency,
            "observed": len(catalog),
            "changed": changed,
            "written": written,
        }
        finalize(session, result)
        session.commit()
        return result
