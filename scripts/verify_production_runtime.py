"""Inventory deployment prerequisites without reading secrets or starting Docker."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from verify_backup_transport import digest, source_fingerprint
from verify_real_model import save


def captured(command, root):
    try:
        result = subprocess.run(
            command, cwd=root, capture_output=True, text=True, timeout=15,
        )
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None, ""


def inventory(root):
    compose_path = root / "docker-config/docker-compose.yml"
    compose = compose_path.read_text(encoding="utf-8")
    config_path = root / "langgraph.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    requirements = (root / "requirements.in").read_text(encoding="utf-8")
    head_exit, head = captured(["git", "rev-parse", "HEAD"], root)
    status_exit, status = captured(["git", "status", "--short"], root)
    context_exit, contexts = captured(["kubectl", "config", "get-contexts", "-o", "name"], root)
    names = (
        "MOONSHOT_API_KEY", "LANGSMITH_API_KEY", "LANGGRAPH_CLOUD_LICENSE_KEY",
        "RESTIC_REPOSITORY", "RESTIC_PASSWORD", "RESTIC_PASSWORD_FILE",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "EVAL_BEARER_TOKEN",
    )
    disks = {}
    for drive in ("C:/", "D:/") if os.name == "nt" else ("/",):
        usage = shutil.disk_usage(drive)
        disks[drive] = {"free_bytes": usage.free, "free_gib": round(usage.free / 1024 ** 3, 4)}
    dotenv = root / ".env"
    metadata = {"exists": dotenv.is_file(), "content_read": False}
    if dotenv.is_file():
        info = dotenv.stat()
        metadata.update(size_bytes=info.st_size, modified_at=datetime.fromtimestamp(
            info.st_mtime, timezone.utc,
        ).isoformat())
    versions = {
        name: re.search(rf"(?m)^{re.escape(name)}(?:\[inmem\])?==([^\s]+)$", requirements).group(1)
        for name in ("langgraph-api", "langgraph-cli")
    }
    uses_dev = '"langgraph"' in compose and '"dev"' in compose
    blockers = [
        "production_target_and_deployment_owner_not_supplied",
        "applicable_license_and_postgres_runtime_not_verified",
        "production_image_digest_and_dependency_compatibility_not_verified",
        "inmem_to_postgres_history_migration_contract_missing",
    ]
    if uses_dev:
        blockers.insert(0, "current_entrypoint_is_development_runtime")
    if os.name == "nt" and disks["C:/"]["free_bytes"] < 10 * 1024 ** 3:
        blockers.append("local_system_disk_below_project_10_gib_runtime_requirement")
    return {
        "format": 1, "recorded_at": datetime.now(timezone.utc).isoformat(),
        "gate": "production_runtime", "outcome": "blocked", "production_decision": "NO-GO",
        "source_head": head if head_exit == 0 else None,
        "source_fingerprint": source_fingerprint(root),
        "application_worktree_clean": not status if status_exit == 0 else None,
        "tracked_runtime_versions": versions,
        "compose_sha256": digest(compose_path),
        "langgraph_config_sha256": digest(config_path),
        "uses_langgraph_dev": uses_dev,
        "postgres_service_declared_in_current_compose": bool(re.search(r"(?m)^  postgres:", compose)),
        "custom_auth_configured": bool(config.get("auth", {}).get("path")),
        "process_configuration_present": {name: bool(os.environ.get(name)) for name in names},
        "local_dotenv_metadata": metadata,
        "kubernetes_context_count": len(contexts.splitlines()) if context_exit == 0 else None,
        "kubernetes_context_probe_exit": context_exit,
        "tool_presence": {name: shutil.which(name) is not None for name in ("docker", "kubectl", "helm", "restic")},
        "disk_space": disks, "docker_operations_started": 0,
        "target_environment_supplied": False, "target_image_or_runtime_verified": False,
        "blockers": blockers,
        "sources": [
            "https://docs.langchain.com/langsmith/deploy-standalone-server",
            "https://docs.langchain.com/langsmith/env-var-self-hosted",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inventory(args.repo_root)
    save(args.output, report)
    print(json.dumps({
        "gate": report["gate"], "outcome": report["outcome"],
        "source_head": report["source_head"], "docker_operations_started": 0,
        "kubernetes_context_count": report["kubernetes_context_count"],
    }))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
