"""Reject cloud deployment libraries requiring newer GLIBC than the target runtime.

The compiled .so files are audited using GNU readelf. The builder uses
manylinux2014 (GLIBC 2.17 baseline), and this check verifies the actual
binary symbols before the ZIP is assembled.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess

_GLIBC = re.compile(r"GLIBC_(\d+)\.(\d+)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, type=pathlib.Path)
    parser.add_argument("--max-glibc", default="2.17")
    args = parser.parse_args()
    allowed = tuple(int(x) for x in args.max_glibc.split("."))
    if len(allowed) != 2:
        raise SystemExit("SCF_GLIBC_TARGET_INVALID")
    if not shutil.which("readelf"):
        raise SystemExit("SCF_READELF_REQUIRED")
    libraries = sorted(args.stage.rglob("*.so"))
    if not libraries:
        raise SystemExit("SCF_NATIVE_LIBRARIES_MISSING")
    highest = (0, 0)
    for library in libraries:
        result = subprocess.run(
            ["readelf", "--version-info", str(library)],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        versions = {tuple(int(v) for v in match) for match in _GLIBC.findall(result.stdout)}
        if versions:
            highest = max(highest, max(versions))
        violations = sorted(version for version in versions if version > allowed)
        if violations:
            raise SystemExit(
                f"SCF_GLIBC_INCOMPATIBLE: {library.relative_to(args.stage)} "
                f"requires {violations[-1]}, allowed {allowed}"
            )
    print(f"SCF_GLIBC_OK: {len(libraries)} native libraries, max needed {highest}")


if __name__ == "__main__":
    main()
