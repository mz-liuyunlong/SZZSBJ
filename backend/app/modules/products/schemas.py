from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    field_validator,
    model_validator,
)

Sku = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
ProductName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
StoreName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
Msku = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
MoneyAmount = Annotated[
    Decimal,
    Field(ge=0, max_digits=18, decimal_places=4),
    PlainSerializer(lambda value: format(value, "f"), return_type=str, when_used="json"),
]


class Platform(StrEnum):
    WALMART = "walmart"
    AMAZON = "amazon"
    TEMU = "temu"
    OTHER = "other"


class ProductSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    @field_validator(
        "purchase_price",
        "wfs_fee",
        "shipping_cost",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def reject_binary_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("monetary values must be decimal strings")
        return value


class ProductMutableFields(ProductSchema):
    category: Annotated[str, StringConstraints(max_length=128)] | None = None
    product_type: Annotated[str, StringConstraints(max_length=128)] | None = None
    status: Annotated[str, StringConstraints(max_length=64)] | None = None
    grade: Annotated[str, StringConstraints(max_length=64)] | None = None
    purchase_price: MoneyAmount | None = None
    currency_code: CurrencyCode | None = None
    declared_cn_name: Annotated[str, StringConstraints(max_length=255)] | None = None
    declared_en_name: Annotated[str, StringConstraints(max_length=255)] | None = None
    material_cn: Annotated[str, StringConstraints(max_length=255)] | None = None
    material_en: Annotated[str, StringConstraints(max_length=255)] | None = None
    remark: str | None = None


class ProductCreate(ProductMutableFields):
    sku: Sku
    product_name: ProductName

    @model_validator(mode="after")
    def validate_currency_pair(self) -> Self:
        if (self.purchase_price is None) != (self.currency_code is None):
            raise ValueError("purchase_price and currency_code must be provided together")
        return self


class ProductUpdate(ProductMutableFields):
    sku: Sku | None = None
    product_name: ProductName | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if "sku" in self.model_fields_set and self.sku is None:
            raise ValueError("sku cannot be null")
        if "product_name" in self.model_fields_set and self.product_name is None:
            raise ValueError("product_name cannot be null")
        if {"purchase_price", "currency_code"} <= self.model_fields_set and (
            (self.purchase_price is None) != (self.currency_code is None)
        ):
            raise ValueError("purchase_price and currency_code must be provided together")
        return self


class ProductRead(ProductSchema):
    id: UUID
    sku: str
    product_name: str
    category: str | None
    product_type: str | None
    status: str | None
    grade: str | None
    purchase_price: MoneyAmount | None
    currency_code: str | None
    declared_cn_name: str | None
    declared_en_name: str | None
    material_cn: str | None
    material_en: str | None
    remark: str | None
    created_at: datetime
    updated_at: datetime


class ProductListQuery(ProductSchema):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sku: Sku | None = None
    product_name: ProductName | None = None
    platform: Platform | None = None
    store_name: StoreName | None = None
    msku: Msku | None = None


class ProductListData(ProductSchema):
    items: list[ProductRead]
    total: int
    page: int
    page_size: int


class ProductOptionsData(ProductSchema):
    platforms: list[Platform]


class ProductListingMutableFields(ProductSchema):
    external_listing_id: Annotated[str, StringConstraints(max_length=255)] | None = None
    listing_url: Annotated[str, StringConstraints(max_length=2048)] | None = None
    listing_status: Annotated[str, StringConstraints(max_length=64)] | None = None
    fulfillment_type: Annotated[str, StringConstraints(max_length=64)] | None = None
    wfs_fee: MoneyAmount | None = None
    shipping_cost: MoneyAmount | None = None
    currency_code: CurrencyCode | None = None


class ProductListingCreate(ProductListingMutableFields):
    platform: Platform
    store_name: StoreName
    msku: Msku

    @model_validator(mode="after")
    def validate_currency_required(self) -> Self:
        if (
            self.wfs_fee is not None or self.shipping_cost is not None
        ) and self.currency_code is None:
            raise ValueError("currency_code is required for monetary values")
        return self


class ProductListingUpdate(ProductListingMutableFields):
    platform: Platform | None = None
    store_name: StoreName | None = None
    msku: Msku | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        for field_name in ("platform", "store_name", "msku"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if (
            {"wfs_fee", "shipping_cost", "currency_code"} <= self.model_fields_set
            and (self.wfs_fee is not None or self.shipping_cost is not None)
            and self.currency_code is None
        ):
            raise ValueError("currency_code is required for monetary values")
        return self


class ProductListingRead(ProductSchema):
    id: UUID
    product_id: UUID
    platform: Platform
    store_name: str
    msku: str
    external_listing_id: str | None
    listing_url: str | None
    listing_status: str | None
    fulfillment_type: str | None
    wfs_fee: MoneyAmount | None
    shipping_cost: MoneyAmount | None
    currency_code: str | None
    created_at: datetime
    updated_at: datetime


class ProductListingListQuery(ProductSchema):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ProductListingListData(ProductSchema):
    items: list[ProductListingRead]
    total: int
    page: int
    page_size: int
