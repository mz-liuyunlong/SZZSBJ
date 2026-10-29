"""Offline original-worker artifact verification; installation requires owner review.

Usage: python -m app.integrations.walmart.worker_artifact ARCHIVE
No automatic deployment, no cloud calls, no credentials read.
"""

from __future__ import annotations

import argparse
import hashlib
import tarfile
from pathlib import Path

EXPECTED_WORKER_SHA256 = "1c510ae6a338fb5359b5007b1e26969cf594c2dd81adc4e162b31785fe29d004"
WORKER_MEMBER = (
    "walmart-remote-pull-it-pack-20261026/features/tools/walmart_remote_pull/run_worker.py"
)


class WorkerArtifactRejected(ValueError):
    """No arbitrary file names or untrusted archive extraction."""


def inspect_original_worker(archive: Path) -> dict[str, object]:
    """Verify exact source member without extracting or writing any file."""
    if not archive.is_file() or archive.is_symlink():
        raise WorkerArtifactRejected("WORKER_ARCHIVE_MISSING")
    try:
        with tarfile.open(archive, mode="r:gz") as package:
            members = [item for item in package.getmembers() if item.name == WORKER_MEMBER]
            if len(members) != 1 or not members[0].isfile():
                raise WorkerArtifactRejected("WORKER_MEMBER_INVALID")
            item = members[0]
            if item.size > 1024 * 1024:
                raise WorkerArtifactRejected("WORKER_MEMBER_TOO_LARGE")
            stream = package.extractfile(item)
            if stream is None:
                raise WorkerArtifactRejected("WORKER_MEMBER_INVALID")
            digest = hashlib.sha256(stream.read(1024 * 1024 + 1)).hexdigest()
            if digest != EXPECTED_WORKER_SHA256:
                raise WorkerArtifactRejected("WORKER_SHA256_MISMATCH")
            return {
                "version": "1.3.2",
                "member": WORKER_MEMBER,
                "sha256": digest,
                "verified": True,
            }
    except (OSError, tarfile.TarError):
        raise WorkerArtifactRejected("WORKER_ARCHIVE_UNREADABLE") from None


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate original Walmart Worker")
    parser.add_argument("archive", type=Path)
    info = inspect_original_worker(parser.parse_args().archive)
    print("Verified Worker v" + str(info["version"]) + " SHA256=" + str(info["sha256"]))


if __name__ == "__main__":
    main()
