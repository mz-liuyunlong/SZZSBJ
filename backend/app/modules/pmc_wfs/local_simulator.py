"""本机模拟 Walmart 通道（Rocky 2026-11-04：在 5173 造数据亲手走一遍待创建货件）。

只在本机生效，硬性条件（任何一条不满足就拒绝，不会退回真实通道）：

* ``PMC_WFS_LOCAL_SIMULATOR=1``；
* ``APP_ENV=local``，数据库是 127.0.0.1 / localhost:55432/szzsbj_dev；
* ``WFS_CREATION_MODE`` 没设（= off）：模拟和真实开关不能同时开。

在别的环境误设了 ``PMC_WFS_LOCAL_SIMULATOR``：``startup_check`` 让服务启动失败（路由模块
导入时调用），``simulator_active`` / ``get_creation_gateway`` 直接报错。

模拟行为和 8088 的真实调用一致：先按单号查（查无此单）→ 创建只返回货件号、不带 FC →
回读给出 FC（LAX2T）→ 箱唛是本地生成的一页 PDF，上面写着「SIMULATED」。退货地址邮编
决定结果：00000 = Walmart 拒绝；99999 = 结果不明（进提交中，下一次拉取查到）；其他 = 成功。
「Walmart 端」已建的单记在本机临时目录的一个 JSON 文件里（种子脚本也写这里）。
这个模块不建网关、不读凭证、没有任何网络调用。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ENV = "PMC_WFS_LOCAL_SIMULATOR"
STATE_ENV = "PMC_WFS_LOCAL_SIMULATOR_STATE"
REJECT_POSTAL = "00000"
UNKNOWN_POSTAL = "99999"
SIM_FC = "LAX2T"
SIM_FC_ADDRESS = {
    "fcName": SIM_FC,
    "addressLine1": "6730 Kimball Ave",
    "city": "Chino",
    "stateCode": "CA",
    "postalCode": "91708",
}
REJECT_REASON = "Invalid returnAddress.postalCode（本机模拟：邮编 00000 一律拒绝）"


class SimulatorRefused(RuntimeError):
    """The simulator switch is set where it must not be. Never falls back to Walmart."""


def requested() -> bool:
    return os.getenv(ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _refuse_reason() -> str | None:
    from app.core.config import get_settings
    from app.modules.pmc_wfs.creation_config import creation_mode

    try:
        settings = get_settings()
        env = settings.app_env.value
        url = settings.sqlalchemy_url()
    except Exception:  # unreadable settings never count as local
        return f"{ENV} 读不到本机配置，拒绝"
    if env != "local":
        return f"{ENV} 只能在 APP_ENV=local 使用（当前 {env}）"
    if creation_mode() != "off":
        return f"{ENV} 不能和 WFS_CREATION_MODE={creation_mode()} 同时设置"
    if url.host not in {"127.0.0.1", "localhost"} or url.port != 55432:
        return f"{ENV} 只能连本机库 127.0.0.1:55432"
    if url.database != "szzsbj_dev":
        return f"{ENV} 只能连本机库 szzsbj_dev"
    return None


def startup_check() -> None:
    """Called when the router module is imported: a misplaced switch stops the service."""
    if requested():
        reason = _refuse_reason()
        if reason:
            raise SimulatorRefused(reason)


def simulator_active() -> bool:
    """True only when the switch is set and every local-only condition holds; raises when the
    switch is set anywhere else."""
    if not requested():
        return False
    reason = _refuse_reason()
    if reason:
        raise SimulatorRefused(reason)
    return True


# ----- 「Walmart 端」状态（本机临时文件）---------------------------------------------------


def state_path() -> Path:
    custom = os.getenv(STATE_ENV)
    return Path(custom) if custom else Path(tempfile.gettempdir()) / "szzsbj_pmc_wfs_simulator.json"


def load_state() -> dict[str, Any]:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: Mapping[str, Any]) -> None:
    path = state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def shipment_id_for(order_id: str, index: int = 0) -> str:
    digest = int(hashlib.sha256(f"{order_id}:{index}".encode()).hexdigest(), 16)
    return f"SIM{digest % 10_000_000:07d}"


def register(order_id: str, shipment_ids: list[str] | None = None) -> list[str]:
    """Record ``order_id`` as created on the simulated Walmart side (used by the seed too)."""
    state = load_state()
    sids = shipment_ids or [shipment_id_for(order_id)]
    state[order_id] = {"shipments": sids}
    save_state(state)
    return sids


def forget(prefix: str = "") -> int:
    state = load_state()
    keep = {k: v for k, v in state.items() if not k.startswith(prefix)} if prefix else {}
    save_state(keep)
    return len(state) - len(keep)


def label_pdf(shipment_id: str, cartons: int | None) -> bytes:
    """A one-page PDF that says SIMULATED, so a printed test label can never be mistaken."""
    text = f"SIMULATED WFS LABEL {shipment_id} CARTONS {cartons or '-'}"
    stream = f"BT /F1 18 Tf 40 400 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


class LocalSimulatorGateway:
    """Implements ``CreationGateway`` without Walmart. Only built by ``get_creation_gateway``
    after ``simulator_active()`` returned True."""

    enabled = True
    preview_enabled = True
    simulator = True
    mode = "simulator"
    reason = None

    def __init__(self) -> None:
        if not simulator_active():
            raise SimulatorRefused(f"{ENV} 未开启")

    @staticmethod
    def store_code(snapshot: Mapping[str, Any]) -> str:
        order = snapshot.get("order") or {}
        name = str(order.get("store_name") or "")
        head = name.split("-", 1)[0].strip().upper()
        if head.isascii() and head.isalnum() and 2 <= len(head) <= 12:
            return head
        return "SIM"

    def validate(self, snapshot: dict) -> None:
        return None

    def create(self, order_id: str, snapshot: dict, allocation: dict) -> list:
        from app.modules.pmc_wfs.walmart_gateway import DefinitiveRejection, ResultUnknown

        postal = str((snapshot.get("return_address") or {}).get("postal_code") or "")
        if postal == REJECT_POSTAL:
            raise DefinitiveRejection(REJECT_REASON)
        sids = register(order_id)
        if postal == UNKNOWN_POSTAL:
            raise ResultUnknown("WALMART_HTTP_504")  # created, but the answer got lost
        return sids  # like 8088: shipment id only, no FC in the create answer

    def reconcile(self, order_id: str, snapshot: dict) -> list | None:
        found = load_state().get(order_id)
        if not found:
            return None  # 8088: HTTP 204
        return [
            {
                "shipment_id": sid,
                "fc": SIM_FC,
                "ship_to": dict(SIM_FC_ADDRESS),
                "status": "PENDING_SHIPMENT_DETAILS",
            }
            for sid in found["shipments"]
        ]

    def label(self, shipment_id: str, snapshot: dict, cartons: int | None = None) -> bytes:
        return label_pdf(shipment_id, cartons)

    def resolve(self, order_id: str, outcome: str, note: str) -> None:
        return None

    def preview(self, snapshot: dict) -> dict:
        return {"ok": True, "shipments": [], "simulated": True}

    def probe(self, store_id: str) -> dict:
        return {
            "ok": True,
            "status_code": 200,
            "store_code": "SIM",
            "recent_shipments": len(load_state()),
            "lookup_status_code": 204,
            "lookup_not_found_ok": True,
        }
