from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from app.modules.integration_sync.data_pages_catalog import DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY
from app.modules.integration_sync.parsers.lingxing_data_pages import (
    DATA_PAGES_PARSER_SPECS,
    DataPagesParserKey,
    ParserFieldSpec,
)

WriteMode = Literal["upsert"]
TargetLayer = Literal["DIM", "FACT"]

SOURCE_METADATA_FIELDS: Final = (
    "source_account_ref",
    "source_raw_request_ref_id",
    "source_observed_at",
    "synced_at",
)

_REFRESH_MARTS_BY_PARSER_KEY: Final[dict[DataPagesParserKey, tuple[str, ...]]] = {
    "seller_list_multi_platform": (
        "mart_daily_sales_item_day",
        "mart_order_profit_sku_day",
        "mart_listing_management_current",
    ),
    "walmart_listing_list": (
        "mart_daily_sales_item_day",
        "mart_order_profit_sku_day",
        "mart_listing_management_current",
    ),
    "sale_stat_page_list": (
        "mart_daily_sales_item_day",
        "mart_order_profit_sku_day",
        "mart_listing_management_current",
    ),
    "order_v2_list": (
        "mart_daily_sales_item_day",
        "mart_order_profit_sku_day",
    ),
    "walmart_return_order_list": (
        "mart_daily_sales_item_day",
        "mart_order_profit_sku_day",
    ),
    "walmart_advertiser_list": (
        "mart_daily_sales_item_day",
        "mart_order_profit_sku_day",
        "mart_listing_management_current",
    ),
    "walmart_ad_item_sp_list": (
        "mart_daily_sales_item_day",
        "mart_order_profit_sku_day",
        "mart_listing_management_current",
    ),
}


@dataclass(frozen=True, slots=True)
class DataPagesWriterSpec:
    """Idempotent writer contract for one DATA-PAGES parser target.

    The spec is metadata-only. It describes how parsed records must be written later;
    it does not read RAW payloads, call Lingxing, or execute database writes by itself.
    """

    parser_key: DataPagesParserKey
    target_table: str
    target_layer: TargetLayer
    write_mode: WriteMode
    unique_key: tuple[str, ...]
    source_record_path: str
    required_source_fields: tuple[str, ...]
    source_metadata_fields: tuple[str, ...]
    refresh_marts: tuple[str, ...]
    boundary_notes: tuple[str, ...]

    @property
    def idempotency_scope(self) -> tuple[str, ...]:
        return (self.target_table, *self.unique_key)


def _target_layer_for_table(target_table: str) -> TargetLayer:
    if target_table.startswith("dim_"):
        return "DIM"
    if target_table.startswith("fact_"):
        return "FACT"
    raise ValueError("DATA_PAGES_WRITER_TARGET_TABLE_UNSUPPORTED")


def _required_source_fields(fields: tuple[ParserFieldSpec, ...]) -> tuple[str, ...]:
    return tuple(field.target_name for field in fields if field.required)


def _writer_spec(parser_key: DataPagesParserKey) -> DataPagesWriterSpec:
    parser_spec = DATA_PAGES_PARSER_SPECS[parser_key]
    sync_spec = DATA_PAGES_SYNC_INTERFACE_SPECS_BY_KEY[parser_key]
    return DataPagesWriterSpec(
        parser_key=parser_key,
        target_table=parser_spec.target_table,
        target_layer=_target_layer_for_table(parser_spec.target_table),
        write_mode="upsert",
        unique_key=parser_spec.unique_key_candidates[0],
        source_record_path=parser_spec.record_path,
        required_source_fields=_required_source_fields(parser_spec.fields),
        source_metadata_fields=SOURCE_METADATA_FIELDS,
        refresh_marts=_REFRESH_MARTS_BY_PARSER_KEY[parser_key],
        boundary_notes=(
            "Use the first approved unique-key candidate for idempotent upsert identity.",
            f"Source interface remains disabled by default: {sync_spec.interface_key}.",
            "Writers must attach RAW request lineage and never persist credentials or payload dumps.",
        ),
    )


DATA_PAGES_WRITER_SPECS: Final[tuple[DataPagesWriterSpec, ...]] = tuple(
    _writer_spec(parser_key) for parser_key in DATA_PAGES_PARSER_SPECS
)

DATA_PAGES_WRITER_SPECS_BY_KEY: Final[dict[DataPagesParserKey, DataPagesWriterSpec]] = {
    spec.parser_key: spec for spec in DATA_PAGES_WRITER_SPECS
}


def data_pages_writer_parser_keys() -> frozenset[DataPagesParserKey]:
    return frozenset(DATA_PAGES_WRITER_SPECS_BY_KEY)


def writer_spec_for(parser_key: DataPagesParserKey) -> DataPagesWriterSpec:
    return DATA_PAGES_WRITER_SPECS_BY_KEY[parser_key]


def writer_target_tables() -> frozenset[str]:
    return frozenset(spec.target_table for spec in DATA_PAGES_WRITER_SPECS)
