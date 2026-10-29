"""Require installed versions and artifact hashes to match the universal lock."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
from pathlib import Path
from urllib.request import urlopen

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.version import Version


def locked_requirements(path: Path) -> dict[str, str]:
    environment = default_environment()
    environment["extra"] = ""
    logical_lines = []
    current = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.partition("#")[0].strip()
        if not stripped:
            continue
        current += " " + stripped.removesuffix("\\").strip()
        if not stripped.endswith("\\"):
            logical_lines.append(current.strip())
            current = ""
    if current:
        raise ValueError("runtime_lock_unterminated_line")
    packages = {}
    for line in logical_lines:
        if line.startswith("--"):
            raise ValueError("runtime_lock_index_override_forbidden")
        requirement_text, separator, hashes = line.partition(" --hash=")
        if not separator or any(
            not re.fullmatch(r"sha256:[0-9a-f]{64}", h.strip())
            for h in hashes.split("--hash=")
        ):
            raise ValueError("runtime_lock_hash_missing")
        requirement = Requirement(requirement_text)
        specifiers = list(requirement.specifier)
        if len(specifiers) != 1 or specifiers[0].operator != "==" or requirement.url:
            raise ValueError("runtime_lock_exact_version_required")
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        version = specifiers[0].version
        Version(version)
        name = requirement.name.lower().replace("_", "-")
        if name in packages and packages[name] != version:
            raise ValueError("runtime_lock_platform_conflict")
        packages[name] = version
    if not packages:
        raise ValueError("runtime_lock_empty")
    return packages


def verify(path: Path, *, check_support=False):
    packages = locked_requirements(path)
    for name, version in packages.items():
        if Version(importlib.metadata.version(name)) != Version(version):
            raise ValueError("runtime_lock_installed_version_mismatch_" + name)
    if check_support:
        with urlopen("https://pypi.org/pypi/langgraph-api/json", timeout=20) as response:
            latest = Version(json.load(response)["info"]["version"])
        current = Version(packages["langgraph-api"])
        if current.is_prerelease or (current.major, current.minor) != (latest.major, latest.minor):
            raise ValueError("runtime_api_not_in_active_support")
    return {"gate": "runtime_lock", "packages": len(packages), "support_checked": check_support}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements", type=Path,
        default=Path(__file__).resolve().parents[1] / "requirements.txt",
    )
    parser.add_argument("--check-support", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.requirements, check_support=args.check_support)))


if __name__ == "__main__":
    main()
