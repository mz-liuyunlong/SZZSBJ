"""Build a minimal Python 3.10 Tencent SCF ZIP without importing the backend app.

Usage (under Python 3.10):
    python -m pip install -r backend/scf-direct-readonly-requirements.txt --target /tmp/scf-stage
    python backend/scripts/build_walmart_scf_direct_bundle.py --stage /tmp/scf-stage --output backend/dist/scf.zip

The target directory must contain only wheel dependencies before this command.
The script intentionally shadows app/__init__.py, whose full backend bootstrap
is NOT part of the cloud function.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys
import zipfile

MODULES = (
    "cloud_executor.py",
    "contract_signing.py",
    "contracts.py",
    "direct_readonly_transport.py",
    "feeds_catalog.py",
    "https_transport.py",
    "marketplace_catalog.py",
    "operations_catalog.py",
    "returns_catalog.py",
    "scf_bridge.py",
    "scf_runtime.py",
    "tencent_api.py",
    "tencent_ssm.py",
    "wfs_catalog.py",
    "wfs_write_catalog.py",
)
PACKAGE = pathlib.Path("app/integrations/walmart")
ENTRYPOINT = "from app.integrations.walmart.scf_runtime import main_handler\n"
ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
MAX_ZIP_BYTES = 50 * 1024 * 1024


def main() -> None:
    if sys.version_info[:2] != (3, 10):
        raise SystemExit("SCF_BUILD_PYTHON310_REQUIRED")
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[2]
    stage = args.stage.resolve()
    if (
        not stage.is_dir()
        or not (stage / "httpx").is_dir()
        or not (stage / "cryptography").is_dir()
    ):
        raise SystemExit("SCF_DEPENDENCIES_MISSING")
    if stage == repo or repo in stage.parents:
        raise SystemExit("SCF_STAGE_MUST_BE_OUTSIDE_REPO")
    source = repo / "backend" / PACKAGE
    if not source.is_dir():
        raise SystemExit("SCF_SOURCE_MISSING")

    # Explicit source allowlist, no backend/__init__ side effects or live secrets.
    manifest = {"runtime": "python3.10", "handler": "index.main_handler", "modules": {}}
    for init in (
        "app/__init__.py",
        "app/integrations/__init__.py",
        "app/integrations/walmart/__init__.py",
    ):
        dest = stage / init
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text('"""Dedicated SCF deployment package."""\n', encoding="utf-8")
    for name in MODULES:
        raw = (source / name).read_bytes()
        compile(raw, str(PACKAGE / name), "exec", dont_inherit=True)
        path = stage / PACKAGE / name
        shutil.copyfile(source / name, path)
        manifest["modules"][name] = hashlib.sha256(raw).hexdigest()
    (stage / "index.py").write_text(ENTRYPOINT, encoding="utf-8")
    (stage / "SCF_BUILD_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if stage == out or stage in out.parents:
        raise SystemExit("SCF_ZIP_MUST_BE_OUTSIDE_STAGE")
    banned = (".env", ".key", ".p12", ".pfx")
    allowed_ca = pathlib.PurePosixPath("certifi/cacert.pem")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(stage)
            if "__pycache__" in relative.parts or relative.suffix == ".pyc":
                continue
            if any(str(relative).endswith(suffix) for suffix in banned) or (
                relative.suffix.lower() == ".pem" and relative != allowed_ca
            ):
                raise SystemExit("SCF_UNEXPECTED_SENSITIVE_FILE")
            info = zipfile.ZipInfo(relative.as_posix(), ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(
                info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
            )
    if out.stat().st_size > MAX_ZIP_BYTES:
        out.unlink()
        raise SystemExit("SCF_BUNDLE_SIZE_EXCEEDED")
    print("SCF_ZIP_OK", out.name, out.stat().st_size, "bytes", len(MODULES), "source modules")


if __name__ == "__main__":
    main()
