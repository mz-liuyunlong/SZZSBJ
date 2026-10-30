"""Register only WFS permission definitions locally; never change any user or role grants."""

import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app.modules.iam.permission_catalog_v2 import PERMISSION_DEFINITIONS  # noqa: E402
from scripts.wfs_pending_local_schema import local_url  # noqa: E402


def main():
    engine = create_engine(local_url(), hide_parameters=True)
    definitions = [asdict(d) for d in PERMISSION_DEFINITIONS
                   if d.page_key in {
                       "pmc_wfs",
                       "pmc_wfs_pending_packing",
                       "pmc_wfs_board",
                       "pmc_wfs_exceptions",
                       "pmc_wfs_settings",
                   }]
    with engine.begin() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("app_permissions")}
        for definition in definitions:
            values = {k: v for k, v in definition.items() if k in columns}
            values["is_active"] = True
            if "group_key" in columns:
                values["group_key"] = "pmc"
            names = list(values)
            conn.execute(text(
                "INSERT INTO app_permissions (" + ",".join(names) + ") VALUES ("
                + ",".join(":" + n for n in names) + ") ON CONFLICT (permission_key) DO NOTHING"
            ), values)
    engine.dispose()
    print("WFS permission definitions registered; user and role grants unchanged")


if __name__ == "__main__":
    main()
