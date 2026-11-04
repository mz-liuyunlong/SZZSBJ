# ruff: noqa: E501, E402, UP031
from __future__ import annotations

from ..readers import cell, norm_head


def header_index(row):
    return {norm_head(h): i for i, h in enumerate(row) if norm_head(h)}


def getter(ix):
    def g(r, k):
        i = ix.get(k)
        return cell(r[i]) if i is not None and i < len(r) else ""

    return g


def blank(r) -> bool:
    return not r or all(cell(x) == "" for x in r)
