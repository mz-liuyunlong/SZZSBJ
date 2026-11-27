"""Read-only SKU grouped pagination and self-excluding facet counts.

No frontend all-page loop, RAW read, provider request, or business write.
All results share one scope, predicates and SKU grouping. Each listing stays
in its original SKU group even when a filter matched only one listing.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from .sku_progress_projection import BASE

FACETS = (
    "store",
    "owner",
    "developer",
    "listing",
    "plan",
    "site",
    "strike",
    "ad",
    "proc",
    "ship",
    "progress",
)
STATIC_VALUES = {
    "listing": ("已上架", "未上架", "待确认"),
    "plan": ("已提交", "未提交", "待确认"),
    "site": ("已提交", "未提交", "待确认"),
    "strike": ("已生效", "未生效", "待确认"),
    "ad": ("已开启", "未开启", "待确认"),
    "proc": ("采购中", "已采购", "国内未到货", "待确认"),
    "ship": ("已发货", "未发货", "待确认"),
    "progress": ("推进中", "已完成", "暂停推进", "终止推进"),
}
CARD_CODES = {
    "all": "",
    "active": "in_progress",
    "done": "completed",
    "paused": "paused",
    "terminated": "terminated",
}
SORTS = {
    "date": "development_at",
    "product": "sku",
    "name": "product_name",
    "dev": "developer_name",
    "progress": "progress_status",
    "listing": "listing_status",
}

# Source statuses and user-owned states are evaluated once per query, on the
# account-scoped projection. PMC matches the exact plan + SKU + store/account,
# not historical procurement for another SKU under the same plan number.
CTE = (
    "WITH scoped AS MATERIALIZED ("
    + BASE
    + (
        "),\n"
        "plans AS MATERIALIZED (\n"
        " SELECT q.id,q.sku_progress_id,q.store_id,q.quantity,q.submission_status,\n"
        " q.lingxing_plan_sn,q.submitted_at,q.cancellation_status,\n"
        " CASE WHEN q.submission_status <> 'submitted' OR q.cancellation_status IN "
        "('requested','unknown','confirmed') THEN NULL\n"
        "      WHEN b.n=0 THEN NULL\n"
        "      WHEN b.waiting THEN 'purchasing'\n"
        "      WHEN b.in_transit THEN 'domestic_not_arrived'\n"
        "      WHEN b.done THEN 'purchased' ELSE NULL END AS purchase_progress\n"
        " FROM scoped s JOIN biz_new_product_sku_purchase_plans q ON "
        "q.sku_progress_id=s.progress_id\n"
        " LEFT JOIN LATERAL (\n"
        "   SELECT count(*) AS n, bool_or(x.stage_code IN ('S1','S2')) AS waiting,\n"
        "    bool_or(x.stage_code IN ('S3','S4')) AS in_transit,\n"
        "    bool_and(x.stage_code='S9') AS done\n"
        "   FROM dws_purchase_board x\n"
        "   WHERE q.submission_status='submitted' AND q.lingxing_plan_sn IS NOT NULL\n"
        "    AND x.source_account_ref=s.source_account_ref AND x.store_id=q.store_id "
        "AND x.sku=s.sku\n"
        "    AND (x.plan_sn=q.lingxing_plan_sn OR "
        "jsonb_exists(x.plan_sns_json,q.lingxing_plan_sn))\n"
        " ) b ON true\n"
        "), plan_groups AS MATERIALIZED (\n"
        " SELECT sku_progress_id,jsonb_agg(to_jsonb(p) ORDER BY p.store_id,p.id) AS "
        "purchase_plans,\n"
        "  CASE WHEN bool_or(submission_status='submitted' AND (cancellation_status IS "
        "NULL OR cancellation_status='failed')) THEN '已提交'\n"
        "       WHEN bool_or(submission_status IN ('submitting','unknown') OR "
        "cancellation_status IN ('requested','unknown')) THEN '待确认'\n"
        "       ELSE '未提交' END AS plan_label,\n"
        "  CASE WHEN bool_or(purchase_progress='purchasing') THEN '采购中'\n"
        "       WHEN bool_or(purchase_progress='domestic_not_arrived') THEN '国内未到货'\n"
        "       WHEN bool_and(purchase_progress='purchased') AND "
        "count(purchase_progress)=count(*) THEN '已采购'\n"
        "       ELSE '待确认' END AS proc_label\n"
        " FROM plans p GROUP BY sku_progress_id\n"
        "), sites AS MATERIALIZED (\n"
        " SELECT t.sku_progress_id,t.target_scope,t.store_id,t.item_id,t.submission_sta"
        "tus,t.submitted_at\n"
        " FROM scoped s JOIN biz_new_product_independent_site_submissions t ON "
        "t.sku_progress_id=s.progress_id\n"
        "), site_groups AS MATERIALIZED (\n"
        " SELECT sku_progress_id,jsonb_agg(to_jsonb(t)) AS "
        "independent_site_submissions\n"
        " FROM sites t GROUP BY sku_progress_id\n"
        "), hydrated AS MATERIALIZED (\n"
        " SELECT s.source_account_ref,s.sku_identity_id,s.sku,s.product_name,s.main_ima"
        "ge_url,\n"
        " s.developer_name,s.developer_uid,s.development_at,\n"
        " (s.development_at AT TIME ZONE 'Asia/Shanghai')::date AS development_date,\n"
        " s.progress_id,s.progress_status,s.remark,s.manual_locked,s.reason_type,s.exit"
        "ed_at,s.progress_version,s.identity_verified,s.updated_at,\n"
        " CASE WHEN NOT s.identity_verified THEN 'unknown'\n"
        "      WHEN jsonb_array_length(s.listings_json)>0 THEN 'listed' ELSE "
        "'unlisted' END AS listing_status,\n"
        " COALESCE(p.purchase_plans,'[]'::jsonb) AS purchase_plans,\n"
        " COALESCE(p.plan_label,'未提交') AS plan_label,COALESCE(p.proc_label,'待确认') AS "
        "proc_label,\n"
        " COALESCE(t.independent_site_submissions,'[]'::jsonb) AS "
        "independent_site_submissions,\n"
        " COALESCE(l.listings,'[]'::jsonb) AS listings,\n"
        " COALESCE(l.store_values,'[]'::jsonb) AS store_values,\n"
        " COALESCE(l.owner_values,'[]'::jsonb) AS owner_values,\n"
        " COALESCE(l.strike_values,'[]'::jsonb) AS strike_values,\n"
        " COALESCE(l.ad_values,'[]'::jsonb) AS ad_values,\n"
        " COALESCE(l.site_values, jsonb_build_array(CASE WHEN EXISTS(\n"
        "  SELECT 1 FROM sites x WHERE x.sku_progress_id=s.progress_id AND "
        "x.target_scope='sku'\n"
        "   AND x.submission_status='submitted') THEN '已提交' ELSE '未提交' END)) AS "
        "site_values,\n"
        " NULL::text AS domestic_shipping_status,20 AS purchase_quantity\n"
        " FROM scoped s LEFT JOIN plan_groups p ON p.sku_progress_id=s.progress_id\n"
        " LEFT JOIN site_groups t ON t.sku_progress_id=s.progress_id\n"
        " LEFT JOIN LATERAL (\n"
        "   SELECT jsonb_agg(j || jsonb_build_object('ad_enabled',effective_ad,'site_la"
        "bel',site_label,\n"
        "        'store_filter',store_filter,'owner_filter',owner_filter) ORDER BY "
        "j->>'store_id',j->>'item_id') AS listings,\n"
        "    jsonb_agg(DISTINCT jsonb_build_object('value',store_filter,'label',COALESC"
        "E(NULLIF(j->>'store_name',''),j->>'store_id')))\n"
        "       FILTER (WHERE NULLIF(j->>'store_id','') IS NOT NULL) AS store_values,\n"
        "    jsonb_agg(DISTINCT jsonb_build_object('value',owner_filter,'label',j->>'ow"
        "ner_ref'))\n"
        "       FILTER (WHERE owner_filter IS NOT NULL) AS owner_values,\n"
        "    jsonb_agg(DISTINCT CASE j->>'strike_effect' WHEN 'effective' THEN '已生效' "
        "WHEN 'ineffective' THEN '未生效' ELSE '待确认' END) AS strike_values,\n"
        "    jsonb_agg(DISTINCT CASE effective_ad WHEN true THEN '已开启' WHEN false THEN "
        "'未开启' ELSE '待确认' END) AS ad_values,\n"
        "    jsonb_agg(DISTINCT site_label) AS site_values\n"
        "   FROM (\n"
        "     SELECT j,\n"
        "      CASE WHEN (j->>'ad_source_observed_at')::timestamptz BETWEEN "
        "now()-interval '48 hours' AND now()\n"
        "           THEN (j->>'ad_enabled')::boolean ELSE NULL END AS effective_ad,\n"
        "      jsonb_build_array(s.source_account_ref,j->>'store_id')::text AS "
        "store_filter,\n"
        "      CASE WHEN NULLIF(btrim(j->>'owner_ref'),'') IS NOT NULL THEN "
        "jsonb_build_array(s.source_account_ref,j->>'owner_ref')::text END AS "
        "owner_filter,\n"
        "      CASE COALESCE((SELECT x.submission_status FROM sites x WHERE "
        "x.sku_progress_id=s.progress_id\n"
        "        AND x.target_scope='listing' AND x.store_id=j->>'store_id' AND "
        "x.item_id=j->>'item_id'),\n"
        "        (SELECT x.submission_status FROM sites x WHERE "
        "x.sku_progress_id=s.progress_id AND x.target_scope='sku'), 'not_submitted')\n"
        "        WHEN 'submitted' THEN '已提交' WHEN 'failed' THEN '未提交' WHEN 'revoked' "
        "THEN '未提交'\n"
        "        WHEN 'not_submitted' THEN '未提交' ELSE '待确认' END AS site_label\n"
        "     FROM jsonb_array_elements(s.listings_json) j\n"
        "   ) listings\n"
        " ) l ON true\n"
        "), ready AS MATERIALIZED (\n"
        " SELECT h.*,\n"
        " jsonb_build_object(\n"
        "  'store',store_values,'owner',owner_values,\n"
        "  'developer',CASE WHEN COALESCE(NULLIF(developer_uid,''),NULLIF(developer_nam"
        "e,'')) IS NULL THEN '[]'::jsonb ELSE\n"
        "     jsonb_build_array(jsonb_build_object('value',jsonb_build_array(source_acc"
        "ount_ref,COALESCE(NULLIF(developer_uid,''),developer_name))::text,\n"
        "      'label',COALESCE(NULLIF(developer_name,''),developer_uid))) END,\n"
        "  'listing',jsonb_build_array(CASE listing_status WHEN 'listed' THEN '已上架' "
        "WHEN 'unlisted' THEN '未上架' ELSE '待确认' END),\n"
        "  'plan',jsonb_build_array(plan_label),'proc',jsonb_build_array(proc_label),'s"
        "ite',site_values,\n"
        "  'ad',CASE WHEN jsonb_array_length(ad_values)=0 THEN '[\"待确认\"]'::jsonb ELSE "
        "ad_values END,\n"
        "  'strike',CASE WHEN jsonb_array_length(strike_values)=0 THEN "
        "'[\"待确认\"]'::jsonb ELSE strike_values END,\n"
        "  'ship','[\"待确认\"]'::jsonb,\n"
        "  'progress',jsonb_build_array(CASE progress_status WHEN 'completed' THEN "
        "'已完成' WHEN 'paused' THEN '暂停推进' WHEN 'terminated' THEN '终止推进' ELSE '推进中' "
        "END)\n"
        " ) AS facets_json\n"
        " FROM hydrated h\n"
        ")\n"
    )
)
KEYWORD = (
    "(:keyword='' OR\n"
    " (:search_field IN ('all','sku') AND strpos(lower(r.sku),lower(:keyword))>0) OR\n"
    " (:search_field IN ('all','name') AND strpos(lower(COALESCE(r.product_name,'')),lo"
    "wer(:keyword))>0) OR\n"
    " (:search_field IN ('all','item') AND EXISTS(SELECT 1 FROM "
    "jsonb_array_elements(r.listings) j\n"
    " WHERE strpos(lower(COALESCE(j->>'item_id','')),lower(:keyword))>0 OR "
    "strpos(lower(COALESCE(j->>'msku','')),lower(:keyword))>0)) OR\n"
    " (:search_field='all' AND EXISTS(SELECT 1 FROM jsonb_array_elements(r.listings) j "
    "WHERE strpos(lower(COALESCE(j->>'store_name','')),lower(:keyword))>0)))"
)
DATE = """(CAST(:start AS date) IS NULL OR r.development_date>=CAST(:start AS date))
 AND (CAST(:end AS date) IS NULL OR r.development_date<=CAST(:end AS date))"""
CARD = "(:card='' OR r.progress_status=:card)"


def facet_expr(key: str) -> str:
    if key not in FACETS:
        raise ValueError("unknown facet")
    return (
        f"(cardinality(CAST(:f_{key} AS text[]))=0 OR EXISTS (SELECT 1 FROM "
        f"jsonb_array_elements(r.facets_json->'{key}') v WHERE "
        f"COALESCE(v->>'value',v#>>'{{}}')=ANY(CAST(:f_{key} AS text[]))))"
    )


def predicates(*, skip: str | None = None, date_filter: bool = True, card: bool = True) -> str:
    parts = [KEYWORD]
    if date_filter:
        parts.append(DATE)
    if card:
        parts.append(CARD)
    parts.extend(facet_expr(k) for k in FACETS if k != skip)
    return " AND ".join(f"({part})" for part in parts)


def params(accounts: frozenset[str], filters: dict[str, Any]) -> dict[str, Any]:
    return dict(
        accounts=sorted(accounts),
        keyword=filters.get("keyword", "").strip(),
        search_field=filters.get("search_field", "all"),
        start=filters.get("start"),
        end=filters.get("end"),
        card=CARD_CODES[filters.get("card", "all")],
        **{f"f_{k}": sorted(set(filters.get(k, ()))) for k in FACETS},
    )


def stmt(sql: str):
    return text(CTE + sql).bindparams(bindparam("accounts", expanding=True))


STATS = """count(*) AS total,
 count(*) FILTER(WHERE progress_status='in_progress') AS in_progress,
 count(*) FILTER(WHERE progress_status='completed') AS completed,
 count(*) FILTER(WHERE progress_status='paused') AS paused,
 count(*) FILTER(WHERE progress_status='terminated') AS terminated,
 count(*) FILTER(WHERE listing_status='listed') AS listed,
 count(*) FILTER(WHERE listing_status='unlisted') AS unlisted,
 COALESCE(sum(jsonb_array_length(listings)),0)::bigint AS listing_count"""


def list_statement(sort_by: str, sort_order: str):
    field = SORTS[sort_by]
    direction = {"asc": "ASC", "desc": "DESC"}[sort_order]
    order = f"{field} {direction} NULLS LAST,source_account_ref,sku_identity_id"
    return stmt(
        ", filtered AS MATERIALIZED (SELECT r.* FROM ready r WHERE "
        f"{predicates()}"
        "),\n"
        " paged AS (SELECT * FROM filtered ORDER BY "
        f"{order}"
        " LIMIT :limit OFFSET :offset)\n"
        " SELECT (SELECT count(*) FROM filtered) AS total,\n"
        " (SELECT COALESCE(sum(jsonb_array_length(listings)),0)::bigint FROM filtered) "
        "AS listing_count,\n"
        " COALESCE((SELECT jsonb_agg(to_jsonb(p)-'facets_json'-'store_values'-'owner_va"
        "lues'-'strike_values'-'ad_values'-'site_values' ORDER BY "
        f"{order}"
        ") FROM paged p),'[]'::jsonb) AS items"
    )


def summary_statement():
    return stmt(f"SELECT {STATS} FROM ready r WHERE {predicates(card=False)}")


def facet_statement():
    # Evaluate each predicate once per SKU, then exclude its own facet. Keep
    # a currently selected zero-count option's real label within the scope.
    tests = ",\n".join(f"{facet_expr(k)} AS match_{k}" for k in FACETS)
    mismatches = "+".join(f"(CASE WHEN match_{k} THEN 0 ELSE 1 END)" for k in FACETS)
    branches = ",\n".join(
        f"('{k}',(r.mismatches=0 OR (r.mismatches=1 AND NOT r.match_{k})),CAST(:f_{k} AS text[]))"
        for k in FACETS
    )
    return stmt(
        " , evaluated AS MATERIALIZED (\n"
        " SELECT r.*,"
        f"{KEYWORD}"
        " AS keyword_match,("
        f"{DATE}"
        ") AS date_match,"
        f"{CARD}"
        " AS card_match,"
        f"{tests}"
        "\n"
        " FROM ready r\n"
        " ), counted AS MATERIALIZED (SELECT e.*,("
        f"{mismatches}"
        ") AS mismatches FROM evaluated e),\n"
        " options AS (\n"
        " SELECT f.key, COALESCE(v->>'value',v#>>'{}') AS value,\n"
        " max(COALESCE(v->>'label',v#>>'{}')) AS label,\n"
        " count(DISTINCT (r.source_account_ref,r.sku_identity_id)) FILTER(\n"
        "    WHERE r.keyword_match AND r.date_match AND r.card_match AND f.matched) AS "
        "count\n"
        " FROM counted r CROSS JOIN LATERAL (VALUES "
        f"{branches}"
        ") f(key,matched,selected)\n"
        " CROSS JOIN LATERAL jsonb_array_elements(r.facets_json->f.key) v\n"
        " WHERE (r.keyword_match AND r.date_match AND r.card_match AND f.matched)\n"
        "  OR COALESCE(v->>'value',v#>>'{}')=ANY(f.selected)\n"
        " GROUP BY f.key,COALESCE(v->>'value',v#>>'{}')\n"
        " ), bounds AS (SELECT min(development_date) AS min_date,max(development_date) "
        "AS max_date\n"
        " FROM counted WHERE keyword_match AND card_match AND mismatches=0)\n"
        " SELECT COALESCE((SELECT jsonb_agg(to_jsonb(o) ORDER BY "
        "o.key,o.label,o.value) FROM options o),'[]'::jsonb) AS options,\n"
        " min_date,max_date FROM bounds"
    )


def list_page(
    db: Session,
    accounts: frozenset[str],
    filters: dict[str, Any],
    *,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
) -> dict:
    if not accounts:
        return {"items": [], "total": 0, "listing_count": 0, "page": page, "page_size": page_size}
    data = (
        db.execute(
            list_statement(sort_by, sort_order),
            {**params(accounts, filters), "limit": page_size, "offset": (page - 1) * page_size},
        )
        .mappings()
        .one()
    )
    return {**dict(data), "page": page, "page_size": page_size}


def summary(db: Session, accounts: frozenset[str], filters: dict[str, Any]) -> dict:
    if not accounts:
        return dict.fromkeys(
            (
                "total",
                "in_progress",
                "completed",
                "paused",
                "terminated",
                "listed",
                "unlisted",
                "listing_count",
            ),
            0,
        )
    return dict(db.execute(summary_statement(), params(accounts, filters)).mappings().one())


def facets(db: Session, accounts: frozenset[str], filters: dict[str, Any]) -> dict:
    data = (
        db.execute(facet_statement(), params(accounts, filters)).mappings().one()
        if accounts
        else {"options": [], "min_date": None, "max_date": None}
    )
    result: dict[str, list[dict]] = {k: [] for k in FACETS}
    for row in data["options"]:
        result[row["key"]].append({k: row[k] for k in ("value", "label", "count")})
    for key, values in STATIC_VALUES.items():
        counts = {r["value"]: r["count"] for r in result[key]}
        result[key] = [{"value": v, "label": v, "count": counts.get(v, 0)} for v in values]
    return {
        "facets": result,
        "date_range": {"min": data["min_date"], "max": data["max_date"]},
        "unknown_sources": ["ship"],
    }


PURCHASE_EVIDENCE = text(
    "\n"
    "SELECT k.account,k.store_id,k.item_id,f.grade,f.data_coverage_json,\n"
    " EXISTS(SELECT 1 FROM biz_new_product_purchase_applications a\n"
    "  WHERE a.source_account_ref=k.account AND a.store_id=k.store_id AND "
    "a.item_id=k.item_id\n"
    "  AND a.status IN ('submitted','approved')) AS existing_approval\n"
    "FROM jsonb_to_recordset(CAST(:keys AS jsonb)) AS k(account text,store_id "
    "text,item_id text)\n"
    "JOIN biz_new_product_registry r ON r.source_account_ref=k.account AND "
    "r.store_id=k.store_id AND r.item_id=k.item_id\n"
    "JOIN biz_new_product_performance_current f ON f.registry_id=r.id\n"
)


def attach_purchase_options(db: Session, data: dict, authorized: bool) -> None:
    """Bounded page-only eligibility hint; the write endpoint always revalidates.

    No token, remote lookup or write. Do not imply that a stale read grants a
    purchase. Existing plan claims (including uncertain ones) disable retries.
    """
    import json
    import os
    import re

    from app.core.api import ApiError

    from .sku_progress_purchase import confirmed_grade

    enabled = (
        authorized
        and os.getenv("SZZSBJ_SKU_PROGRESS_PURCHASE_ENABLED", "").strip().upper() == "YES"
        and not os.getenv("NEW_PRODUCTS_READ_DATABASE_URL", "").strip()
    )
    keys = []
    candidates = []
    for row in data["items"]:
        blocked = {p["store_id"] for p in row["purchase_plans"]}
        for listing in row["listings"]:
            listing["purchase_candidate"] = False
            if (
                enabled
                and row["identity_verified"]
                and row["progress_status"] == "in_progress"
                and row.get("exited_at") is None
                and listing["store_id"] not in blocked
                and re.fullmatch(r"[0-9]{11}", str(listing.get("item_id") or ""))
                and re.fullmatch(
                    r"(?:[0-9]{8}|[0-9]{12}|[0-9]{13}|[0-9]{14})", str(listing.get("gtin") or "")
                )
            ):
                key = (row["source_account_ref"], listing["store_id"], listing["item_id"])
                keys.append(dict(zip(("account", "store_id", "item_id"), key, strict=True)))
                candidates.append((key, listing))
    if not keys:
        return
    evidence = {}
    for record in db.execute(PURCHASE_EVIDENCE, {"keys": json.dumps(keys)}).mappings():
        key = (record["account"], record["store_id"], record["item_id"])
        try:
            confirmed_grade(record["grade"], record["data_coverage_json"])
        except ApiError:
            continue
        if not record["existing_approval"]:
            evidence[key] = True
    for key, listing in candidates:
        listing["purchase_candidate"] = bool(evidence.get(key))
