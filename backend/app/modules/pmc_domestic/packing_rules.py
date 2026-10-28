"""Pure stock proof and source fingerprint rules; never infer stock from order counts."""

import hashlib
import json
from datetime import UTC, date, datetime


def available_good_stock(components):
    if not components:
        return None, None, None
    good = locked = 0
    for b in components:
        values = []
        for key in ("good_num", "storage_used_lock_num"):
            value = b.get(key)
            if isinstance(value, bool) or value is None or not str(value).isdigit():
                return None, None, None
            values.append(int(value))
        if values[1] > values[0]:
            return None, None, None
        good += values[0]
        locked += values[1]
    return good, locked, good - locked


def fingerprint(value):
    def canonical(item):
        if isinstance(item, datetime):
            return item.astimezone(UTC).isoformat()
        if isinstance(item, date):
            return item.isoformat()
        return str(item)

    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            default=canonical,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def listing_version(row):
    """Bind the user's final identity choice to the complete current Listing proof."""
    return fingerprint(
        [
            str(row.id),
            row.source_account_ref,
            row.store_id,
            row.local_sku,
            row.item_id,
            row.gtin,
            row.msku,
            row.standard_status,
            row.fulfillment_type,
            row.business_hash,
        ]
    )


def listing_blocked_reasons(row):
    """Candidate projection and final decisions require the same Listing proof."""
    blocked = []
    if row is None:
        return ["ELIGIBLE_LISTING_MISSING"]
    if row.standard_status != "PUBLISHED" or not (row.item_url or "").strip():
        blocked.append("ELIGIBLE_LISTING_MISSING")
    if row.fulfillment_type != "1":
        blocked.append("WFS_NOT_CONVERTED")
    if not row.gtin or not row.gtin.isdigit() or len(row.gtin) != 14:
        blocked.append("GTIN_INVALID")
    if not row.msku:
        blocked.append("MSKU_MISSING")
    return blocked
