"""把一个文件跑完：识别 → 解析 → 标准化 → 指纹 → 文件内排序 → 余额链。认不出就抛 RejectFile。"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree.ElementTree import ParseError

from . import detector, parsers
from .fingerprint import assign_uids
from .model import Line, RejectFile
from .normalize import normalize
from .seed import Seed

UNEXPECTED_PARSE_ERRORS = (
    ValueError,
    KeyError,
    IndexError,
    TypeError,
    ArithmeticError,
    StopIteration,
    UnicodeError,
    ParseError,
)


@dataclass
class ParsedFile:
    provider: str
    note: str
    lines: list[Line]
    declared_range: tuple[str, str] | None
    balance_chain_ok: bool
    warnings: list[str] = field(default_factory=list)


def _bank_order(lines: list[Line]) -> None:
    """按账户判断导出方向（旧→新 / 新→旧），把文件行号归一成时间正序号。"""
    by_account: dict[str, list[Line]] = {}
    for line in lines:
        by_account.setdefault(line.account_key, []).append(line)
    for group in by_account.values():
        group.sort(key=lambda x: (x.statement_row_no, x.amount < 0))
        keys = [(x.business_date, x.source_time_utc) for x in group]
        up = sum(1 for a, b in zip(keys, keys[1:], strict=False) if b > a)
        down = sum(1 for a, b in zip(keys, keys[1:], strict=False) if b < a)
        ordered = group if up >= down else list(reversed(group))
        for index, line in enumerate(ordered, start=1):
            line.file_row_order = index


def _broken_chains(lines: list[Line], seed: Seed) -> list[str]:
    by_account: dict[str, list[Line]] = {}
    for line in lines:
        by_account.setdefault(line.account_key, []).append(line)
    broken: list[str] = []
    for account_key, group in by_account.items():
        if seed.accounts[account_key].provider == "pingpong":
            continue  # PingPong 子账户不做链校验
        previous = None
        for line in sorted(group, key=lambda x: x.file_row_order):
            if line.balance_after is None:
                continue
            if previous is not None and previous + line.amount != line.balance_after:
                broken.append(account_key)
                break
            previous = line.balance_after
    return broken


def parse_file(content: bytes, seed: Seed) -> ParsedFile:
    try:
        detection = detector.detect(content, seed)
        rows = parsers.parse(detection, seed)
        lines = [normalize(row) for row in rows]
    except RejectFile:
        raise
    except UNEXPECTED_PARSE_ERRORS as exc:
        raise RejectFile("文件内容解析失败，请确认是银行 / 平台的原始导出") from exc
    if not lines:
        raise RejectFile("文件里没有可入库的流水")
    assign_uids(lines)
    _bank_order(lines)
    warnings: list[str] = []
    broken = _broken_chains(lines, seed)
    if broken:
        warnings.append("余额链断开：" + ",".join(sorted(set(broken))))
    if detection.skipped_rows:
        warnings.append(f"跳过 {detection.skipped_rows} 行重复表头或汇总行")
    declared = detection.declared_range
    if declared:
        first = min(line.business_date for line in lines).isoformat()
        last = max(line.business_date for line in lines).isoformat()
        if first < declared[0] or last > declared[1]:
            warnings.append("流水日期超出表头声明区间")
    return ParsedFile(
        provider=detection.provider,
        note=detection.note,
        lines=lines,
        declared_range=declared,
        balance_chain_ok=not broken,
        warnings=warnings,
    )
