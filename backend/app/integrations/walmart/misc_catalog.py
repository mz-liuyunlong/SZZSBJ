"""Smaller US Marketplace read contracts probed OK on 2026-10-08: lag time, taxonomy,
single-SKU inventories, shipping settings / templates / nodes, Shipping-with-Walmart
carrier metadata, webhook metadata. All GET; none changes seller data.

Endpoints whose parameters are not documented on the pages we hold are registered without
query fields (the 2026-10-08 probe succeeded without parameters); passing a parameter is
refused by the contract rather than forwarded blindly.
"""

from __future__ import annotations

from app.integrations.walmart._catalog_base import enabled_registry
from app.integrations.walmart.contracts import ContractRegistry, Field, Operation

_REF = "https://developer.walmart.com/us-marketplace/reference/"
_OPERATIONS = (
    Operation(
        key="lagtime_get",
        method="GET",
        path="/v3/lagtime",
        fields=(Field("sku", "query", required=True),),
        source=_REF + "getlagtime",
    ),
    Operation(
        key="items_taxonomy",
        method="GET",
        path="/v3/items/taxonomy",
        fields=(Field("version", "query", enum=("4.0", "5.0")),),
        source=_REF + "gettaxonomy",
    ),
    Operation(
        key="utilities_taxonomy",
        method="GET",
        path="/v3/utilities/taxonomy",
        fields=(),
        source=_REF + "getutilitiestaxonomy",
    ),
    Operation(
        key="inventories_sku_get",
        method="GET",
        path="/v3/inventories/{sku}",
        fields=(Field("sku", "path", required=True),),
        source=_REF + "getmultinodeinventoryforallskusandallshipnodes",
    ),
    Operation(
        key="shipping_templates_list",
        method="GET",
        path="/v3/settings/shipping/templates",
        fields=(),
        source=_REF + "getalltemplates",
    ),
    Operation(
        key="shipping_template_get",
        method="GET",
        path="/v3/settings/shipping/templates/{templateId}",
        fields=(Field("templateId", "path", required=True),),
        source=_REF + "gettemplate",
    ),
    Operation(
        key="shipping_shipnodes_list",
        method="GET",
        path="/v3/settings/shipping/shipnodes",
        fields=(),
        source=_REF + "getfulfillmentcenters",
    ),
    Operation(
        key="shipping_profile_get",
        method="GET",
        path="/v3/settings/shippingprofile",
        fields=(),
        source=_REF + "getshippingprofile",
    ),
    Operation(
        key="sww_carriers_list",
        method="GET",
        path="/v3/shipping/labels/carriers",
        fields=(),
        source=_REF + "getcarriers",
    ),
    Operation(
        key="sww_package_types_list",
        method="GET",
        path="/v3/shipping/labels/carriers/{carrierShortName}/package-types",
        fields=(Field("carrierShortName", "path", required=True),),
        source=_REF + "getpackagetypes",
    ),
    Operation(
        key="sww_ship_on_date_get",
        method="GET",
        path="/v3/shipping/ship-nodes/{shipNodeId}/ship-on-date",
        fields=(Field("shipNodeId", "path", required=True),),
        source=_REF + "getshipondate",
    ),
    Operation(
        key="webhooks_event_types",
        method="GET",
        path="/v3/webhooks/eventTypes",
        fields=(),
        source=_REF + "geteventtypes",
    ),
    Operation(
        key="webhooks_subscriptions_list",
        method="GET",
        path="/v3/webhooks/subscriptions",
        fields=(),
        source=_REF + "getallsubscriptions",
    ),
)


def misc_read_registry(*, approved_keys: frozenset[str] = frozenset()) -> ContractRegistry:
    return enabled_registry(_OPERATIONS, approved_keys)
