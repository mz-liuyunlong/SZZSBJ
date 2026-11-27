# ruff: noqa: E501, E402, UP031
from __future__ import annotations

from ..model import RejectFile
from . import boc, cmb, payoneer, pingpong, shenzhen_rural_bank, worldfirst

PARSERS = {
    "boc": boc.parse,
    "shenzhen_rural_bank": shenzhen_rural_bank.parse,
    "payoneer": payoneer.parse,
    "worldfirst": worldfirst.parse,
    "pingpong": pingpong.parse,
    "cmb": cmb.parse,
}


def parse(detection, seed):
    fn = PARSERS.get(detection.provider)
    if fn is None:
        raise RejectFile("没有对应解析器")
    return fn(detection, seed)
