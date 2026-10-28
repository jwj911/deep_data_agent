"""The container runner must start its browser controller without backend deps."""

import subprocess
import sys
from pathlib import Path


def test_browser_controller_starts_without_site_packages():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-S", "-B", str(root / "scripts/verify_browser_smoke.py"), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "--playwright-module" in result.stdout
