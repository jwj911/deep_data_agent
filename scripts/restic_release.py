"""Verify and unpack an already downloaded, digest-pinned restic release."""
from __future__ import annotations

import argparse
import bz2
import hashlib
import io
import os
import platform
import zipfile
from pathlib import Path

VERSION = "0.19.1"
RELEASES = {
    "Windows": {
        "archive": "restic_0.19.1_windows_amd64.zip",
        "archive_sha256": "da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d",
        "binary_sha256": "b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830",
    },
    "Linux": {
        "archive": "restic_0.19.1_linux_amd64.bz2",
        "archive_sha256": "f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c",
        "binary_sha256": "20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639",
    },
}


def release():
    if platform.machine().lower() not in ("amd64", "x86_64"):
        raise ValueError("restic_architecture_unsupported")
    try:
        return RELEASES[platform.system()]
    except KeyError as exc:
        raise ValueError("restic_platform_unsupported") from exc


def verify_binary(path: Path) -> dict:
    selected = release()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("restic_binary_invalid")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha != selected["binary_sha256"]:
        raise ValueError("restic_binary_digest_mismatch")
    return {"version": VERSION, "platform": platform.system(), "sha256": sha}


def install_archive(archive: Path, output: Path):
    selected = release()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("restic_output_must_be_new")
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("restic_archive_invalid")
    raw = archive.read_bytes()
    if hashlib.sha256(raw).hexdigest() != selected["archive_sha256"]:
        raise ValueError("restic_archive_digest_mismatch")
    if platform.system() == "Windows":
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            entries = [name for name in source.namelist() if name.endswith(".exe")]
            if len(entries) != 1:
                raise ValueError("restic_archive_layout_invalid")
            binary = source.read(entries[0])
    else:
        binary = bz2.decompress(raw)
    if hashlib.sha256(binary).hexdigest() != selected["binary_sha256"]:
        raise ValueError("restic_binary_digest_mismatch")
    # Fixed trusted bytes, exclusive creation; no archive-controlled extraction paths.
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o700)
    with os.fdopen(descriptor, "wb") as target:
        target.write(binary)
    return verify_binary(output)


def main():
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = install_archive(args.archive, args.output)
    except (OSError, ValueError, zipfile.BadZipFile):
        print(json.dumps({"outcome": "failed", "code": "restic_release_verification_failed"}))
        return 1
    print(json.dumps({"outcome": "passed", **report}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
