"""结算利润 V2 calculation (PRP ``PRPs/finance-settlement-profit-v2.md`` §8).

``engine`` is a pure function over in-memory inputs (``inputs``); ``persistence`` writes
its result to the PR-1 tables with calc_version / content hash / month-close freezing.
"""
