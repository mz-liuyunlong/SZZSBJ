"""8088 defaults for WFS settings (``features/pmc-wfs-shipment/drafts/src/app-d.jsx``
``RULE_ROWS_INIT`` and ``app-b.jsx`` ``CREATE_DEFAULTS_INIT``), frozen as data.

Migration 0077 writes ``RULE_ROWS`` as rule version 1; creation defaults are returned when
an account has no saved row. ``decided=False`` rows are the five 8088 sample thresholds
(PRP S3: shown as 「示例 · 待定」 until Rocky sets them).
"""

from __future__ import annotations

from typing import Final

SEED_VERSION_EFFECTIVE: Final = "2026-10-10"
SEED_REASON: Final = "8088 WFS 设置页默认值（RULE_ROWS_INIT，WFS-RULES-20261010）"
SEED_ACTOR: Final = "system:8088-seed"

# (rule_key, node, region, carrier, channel, days, remind, effective, notify, remark, decided)
RULE_ROWS: Final[tuple[tuple, ...]] = (
    (
        "deliveredNotSigned",
        "货代签收 → Walmart 未签收且 Received = 0",
        "全部",
        "全部",
        "全部",
        3,
        0,
        "2026-10-10",
        "物流组 · WFS 组（飞书）",
        "Rocky 2026-10-10 定：货代签收满 3 天；Walmart 一签收即停止本条",
        True,
    ),
    (
        "draftRemind",
        "待创建货件未处理",
        "—",
        "—",
        "—",
        3,
        0,
        "2026-09-21",
        "WFS 组（企业微信）",
        "不自动释放，只提醒",
        True,
    ),
    (
        "internalWarn",
        "收货差异内部预警（自 D0）",
        "全部",
        "全部",
        "全部",
        7,
        0,
        "2026-09-21",
        "WFS 组",
        "D+7 公司内部规则（v3 §21）",
        True,
    ),
    (
        "etaOverdue",
        "预计到仓已过 → Walmart 未签收",
        "全部",
        "全部",
        "全部",
        7,
        2,
        "2026-09-21",
        "物流组 · WFS 组",
        "示例阈值；预计到仓取领星 arrival_time（待核实）",
        False,
    ),
    (
        "diffTol",
        "短少容差（单个 SKU 差异 ≤ N 件不算异常；超收不算异常）",
        "全部",
        "全部",
        "全部",
        10,
        0,
        "2026-10-10",
        "WFS 组",
        "Rocky 2026-10-10 定（可配置）",
        True,
    ),
    (
        "signNoReceipt",
        "Walmart 签收 → 开始上架（满 N 天无 Receipt）",
        "全部",
        "全部",
        "全部",
        10,
        0,
        "2026-10-10",
        "WFS 组",
        "Rocky 2026-10-10 定：自 Walmart 签收日起预留 10 天",
        True,
    ),
    (
        "receivingStuck",
        "Walmart 签收 → 收完（满 N 天未收完 = 收货长期未完成）",
        "全部",
        "全部",
        "全部",
        15,
        0,
        "2026-10-10",
        "WFS 组",
        "Rocky 2026-10-10 定：自 Walmart 签收日起算，单级，不设提示级",
        True,
    ),
    (
        "pendingNoShip",
        "创建后长期未发货",
        "—",
        "—",
        "—",
        7,
        0,
        "2026-09-21",
        "仓库 · WFS 组",
        "示例阈值，待 Rocky 定",
        False,
    ),
    (
        "disputeUrgent",
        "Dispute 临近截止提醒（剩余天数 ≤）",
        "全部",
        "全部",
        "全部",
        5,
        0,
        "2026-09-21",
        "WFS 组 · 主管（钉钉）",
        "示例阈值",
        False,
    ),
    (
        "portToDelivered",
        "到港 → 物流 Delivered 超时",
        "美西",
        "全部",
        "全部",
        5,
        1,
        "2026-09-21",
        "物流组",
        "示例：按地区分别配置",
        False,
    ),
    (
        "portToDelivered",
        "到港 → 物流 Delivered 超时",
        "美东",
        "全部",
        "全部",
        8,
        1,
        "2026-09-21",
        "物流组",
        "示例：美东卡派更久",
        False,
    ),
)
RULE_FIELDS: Final = (
    "rule_key",
    "node",
    "region",
    "carrier",
    "channel",
    "days",
    "remind_days",
    "row_effective_date",
    "notify",
    "remark",
    "decided",
)

# Rocky 2026-09-22 (8088 CREATE_DEFAULTS_INIT).
CREATION_DEFAULTS: Final = {
    "transport": "LTL",
    "ship_date_offset": 15,
    "pallet_boxes": 16,
    "mixed_boxes": 0,
    "carrier_opt": "own",
}
