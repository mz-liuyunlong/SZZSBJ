"""Owner-verified corrections where the derived Lingxing interface index is inaccurate."""

from __future__ import annotations

from typing import Literal

type HttpMethod = Literal["GET", "POST", "DELETE"]

# The repository registry was generated from normalized metadata. The owner's complete
# documentation snapshot shows these five method values differ from that derived index.
# Keep the corrections explicit and reviewable rather than silently rewriting source data.
OFFICIAL_HTTP_METHOD_OVERRIDES: dict[str, HttpMethod] = {
    "LX-ECC5B6E072BC": "POST",  # 删除出库单
    "LX-50E3A9271BE9": "POST",  # 删除调拨单
    "LX-9AE1466FB085": "POST",  # 删除备货单
    "LX-1E89A7A2DA3C": "POST",  # 删除费用单
    "LX-2AD144D844C7": "POST",  # 查询 settlement 下载 URL
}


def official_http_method(interface_id: str, indexed_method: HttpMethod) -> HttpMethod:
    """Return the method verified from the complete owner-provided documentation."""

    return OFFICIAL_HTTP_METHOD_OVERRIDES.get(interface_id, indexed_method)
