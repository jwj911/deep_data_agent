"""Pinning and hash checks reject drift rather than silently resolving it."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_runtime_lock


@pytest.mark.parametrize("line", [
    "httpx>=0.28 --hash=sha256:" + "a" * 64,
    "httpx==0.28.1",
    "httpx==0.28.1 --hash=md5:" + "a" * 32,
    "--index-url https://example.invalid",
    "httpx @ https://example.invalid/pkg.whl --hash=sha256:" + "a" * 64,
])
def test_unlocked_or_untrusted_install_is_rejected(tmp_path, line):
    path = tmp_path / "requirements.txt"
    path.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        verify_runtime_lock.locked_requirements(path)


def test_platform_markers_select_only_active_pin(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text(
        'httpx==0.28.1 \\\n --hash=sha256:' + "a" * 64
        + '\nuvloop==0.22.1 ; sys_platform == "never" \\\n --hash=sha256:' + "b" * 64 + "\n",
        encoding="utf-8",
    )
    assert verify_runtime_lock.locked_requirements(path) == {"httpx": "0.28.1"}


def test_installed_drift_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "requirements.txt"
    path.write_text("httpx==0.28.1 --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    monkeypatch.setattr(verify_runtime_lock.importlib.metadata, "version", lambda _: "0.28.0")
    with pytest.raises(ValueError, match="version_mismatch"):
        verify_runtime_lock.verify(path)
