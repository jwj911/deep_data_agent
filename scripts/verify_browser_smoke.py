"""Connect an isolated five-service browser drill to a controlled TCP provider."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from verify_agent_budget_http import ControlledProvider, serve_provider
from verify_container_smoke import ComposeContext, SmokeError, _compose_output


def _configure(context):
    result = subprocess.run(
        context.command(
            "up", "-d", "--no-build", "--wait", "--wait-timeout", "120",
            "fastapi", "langgraph",
        ), capture_output=True, timeout=180,
    )
    if result.returncode:
        raise SmokeError("browser_drill_configuration_failed")


def verify(context, module, scratch_root):
    if not context.project_name.startswith("dda-"):
        raise SmokeError("browser_drill_requires_isolated_dda_project")
    root = Path(__file__).resolve().parents[1]
    provider = ControlledProvider("browser")
    with serve_provider(provider, host="0.0.0.0") as base:
        with tempfile.TemporaryDirectory(prefix="dda-browser-", dir=scratch_root) as scratch:
            override = Path(scratch) / "provider.yml"
            override.write_text(
                "services:\n" + "".join(
                    f"  {service}:\n"
                    "    extra_hosts:\n      - 'host.docker.internal:host-gateway'\n"
                    "    environment:\n"
                    f"      MODEL_BASE_URL: 'http://host.docker.internal:{urlparse(base).port}/v1'\n"
                    for service in ("fastapi", "langgraph")
                ), encoding="utf-8",
            )
            controlled = ComposeContext(
                (*context.compose_files, override), context.env_file, context.project_name,
            )
            try:
                _configure(controlled)
                result = subprocess.run(
                    ["node", str(root / "scripts/verify_browser_smoke.mjs")],
                    env=dict(os.environ, DDA_PLAYWRIGHT_MODULE=str(module)),
                    capture_output=True, text=True, timeout=240,
                )
                if result.returncode:
                    try:
                        stage = json.loads(result.stdout.strip())["stage"]
                    except (ValueError, KeyError):
                        stage = "browser_process"
                    raise SmokeError("browser_drill_failed_" + stage)
                receipt = json.loads(result.stdout.strip())
                if receipt.get("outcome") != "passed" or provider.requests != 1:
                    raise SmokeError("browser_drill_provider_count_invalid")
                leases = _compose_output(
                    context, "exec", "-T", "redis", "redis-cli", "--scan",
                    "--pattern", "agent:lease:*", operation="browser lease cleanup",
                )
                if leases.strip():
                    raise SmokeError("browser_drill_lease_keys_remain")
                return {**receipt, "received_requests": provider.requests, "remaining_lease_keys": 0}
            finally:
                _configure(context)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", action="append", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--playwright-module", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path)
    args = parser.parse_args()
    context = ComposeContext(tuple(args.compose_file), args.env_file, args.project_name)
    try:
        print(json.dumps(verify(context, args.playwright_module, args.scratch_root)))
    except (SmokeError, subprocess.TimeoutExpired) as exc:
        code = str(exc) if isinstance(exc, SmokeError) else "browser_drill_timeout"
        print(json.dumps({"gate": "browser_ui", "outcome": "failed", "code": code}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
