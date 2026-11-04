"""Shared SQL eligibility for WFS clearance analysis and manual selection.

Only current verified WFS inventory and non-archived Listings are eligible.
The predicate is applied BEFORE daily evidence evaluation, SQL paging,
aggregates, and manual application checks. It must use Listing alias "l"
and latest WFS inventory alias "snap".
"""

ACTIVE_WFS_LISTING_SQL = """
    l.wfs_available_quantity > 0
    and snap.wfs_available_quantity > 0
    and snap.captured_at >= now() - interval '72 hours'
    and snap.captured_at <= now()
    and not exists (
        select 1 from listing_archive_states archived
        where archived.listing_id = l.id
          and archived.source_account_ref = l.source_account_ref
          and archived.store_id = l.store_id
          and archived.item_id = l.item_id
          and archived.is_archived = true
    )
"""
