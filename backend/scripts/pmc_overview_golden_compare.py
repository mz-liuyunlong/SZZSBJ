"""Compare the overview rule layer with an 8088 golden snapshot (local file only).

Usage:
  uv run python scripts/pmc_overview_golden_compare.py <golden.json> \
      [--draft-mode demo_8088|replenishment]
No network, no database.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from app.modules.pmc_overview.golden import compare_snapshot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--draft-mode", default="demo_8088", choices=["demo_8088", "replenishment"])
    a = ap.parse_args()
    with open(a.snapshot, encoding="utf-8") as f:
        snap = json.load(f)
    res = compare_snapshot(snap, a.draft_mode)
    print("items", len(snap["items"]), "draft_mode", a.draft_mode)
    print("kpi_diff", json.dumps(res["kpi_diff"], ensure_ascii=False))
    print("item_diffs", len(res["item_diffs"]))
    fields = Counter(k for d in res["item_diffs"] for k in d["diff"])
    print("diff_fields", dict(fields))
    for d in res["item_diffs"][:10]:
        print(json.dumps(d, ensure_ascii=False))
    return 0 if not res["kpi_diff"] and not res["item_diffs"] else 1


if __name__ == "__main__":
    sys.exit(main())
