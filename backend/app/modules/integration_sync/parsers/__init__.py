"""Versioned parsers for approved synthetic and persisted RAW inputs."""

from app.modules.integration_sync.parsers.lingxing_data_pages import (
    DATA_PAGES_PARSER_SPECS,
    DataPagesParserSpec,
    ParserFieldSpec,
    get_data_pages_parser_spec,
)

__all__ = [
    "DATA_PAGES_PARSER_SPECS",
    "DataPagesParserSpec",
    "ParserFieldSpec",
    "get_data_pages_parser_spec",
]
