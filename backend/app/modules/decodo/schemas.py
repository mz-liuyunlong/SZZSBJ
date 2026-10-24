"""Explicitly normalized Decodo payloads; never expose credentials or raw HTML."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DecodoConfigRead(BaseModel):
    configured: bool
    enabled: bool
    us_zip: str
    updated_at: datetime | None = None
    updated_by: str | None = None
    mode: Literal["database", "local_test"] = "database"


class DecodoConfigWrite(BaseModel):
    authorization: str | None = Field(default=None, max_length=1024, repr=False)
    us_zip: str = Field(pattern=r"^[0-9]{5}$")
    enabled: bool = False


class DecodoUsageRow(BaseModel):
    date: date
    amazon_requests: int = 0
    walmart_requests: int = 0
    success: int = 0
    failed: int = 0
    pending: int = 0
    total: int = 0


class DecodoUsageRead(BaseModel):
    timezone: Literal["America/New_York"] = "America/New_York"
    today: date
    days: list[DecodoUsageRow]


class WalmartConfirmRequest(BaseModel):
    sku_id: str = Field(min_length=1, max_length=128)
    item_id: str = Field(pattern=r"^[0-9]{1,20}$")


class AmazonResearchRequest(BaseModel):
    sku_id: str = Field(min_length=1, max_length=128)
    asins: list[str] = Field(min_length=1, max_length=20)

    @field_validator("asins")
    @classmethod
    def validate_asins(cls, values: list[str]) -> list[str]:
        # ASIN format is intentionally not restricted to a specific prefix or 10 characters.
        normalized = [x.strip().upper() for x in values]
        if any(not x or len(x) > 128 or any(c.isspace() for c in x) for x in normalized):
            raise ValueError(
                "Each identifier must be a single non-empty token (at most 128 characters)"
            )
        if len(normalized) != len(set(normalized)):
            raise ValueError("Duplicate identifiers are not accepted")
        return normalized


class WalmartFactRead(BaseModel):
    snapshot_id: str | None = None
    gtin: str | None = None
    seller_name: str | None = None
    item_id: str
    sku_id: str
    title: str
    brand: str | None = None
    description: str | None = None
    category_path: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    main_image: str | None = None
    gallery_images: list[str] = Field(default_factory=list)
    url: str | None = None
    source: Literal["decodo"] = "decodo"
    verified: bool = True
    fetched_at: datetime


class AmazonEvidenceRead(BaseModel):
    snapshot_id: str | None = None
    asin: str
    title: str
    brand: str | None = None
    manufacturer: str | None = None
    bullet_points: list[str] = Field(default_factory=list)
    description: str | None = None
    category_path: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    main_image: str | None = None
    gallery_images: list[str] = Field(default_factory=list)
    url: str | None = None
    source: Literal["decodo"] = "decodo"
    verified: bool = True
    fetched_at: datetime


class AmazonResearchResult(BaseModel):
    items: list[AmazonEvidenceRead]
    failures: list[str] = Field(default_factory=list)
    requested: int
    completed: int
