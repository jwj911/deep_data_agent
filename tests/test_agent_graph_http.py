"""Regression at the real TCP/API seam, with no external service credentials."""

import json
import subprocess
import sys
from pathlib import Path


def test_installed_api_runs_over_tcp_with_preserved_graph_dependencies():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "verify_agent_graph_http.py"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    evidence = json.loads(result.stdout)
    assert evidence["status"] == "passed"
    assert evidence["transport"] == "TCP HTTP"
    assert evidence["leases"] == {"acquired": 3, "released": 3}
    assert evidence["outbound_attempts"] == 0
    assert len(evidence["checks"]) == 10
