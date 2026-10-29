"""Keep packaged verifier entrypoints portable and binary validation fail-closed."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import restic_release
import verify_production_runtime

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.mark.parametrize("name", [
    "verify_backup_transport.py", "verify_production_runtime.py",
    "verify_production_support.py", "verify_real_model.py",
    "verify_recovery_admission.py", "restic_release.py",
])
def test_helper_help_works_outside_repository(tmp_path, name):
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / name), "--help"],
        cwd=tmp_path, env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_modified_archive_never_creates_executable(tmp_path):
    archive = tmp_path / "modified-archive"
    archive.write_bytes(b"untrusted-release")
    output = tmp_path / "restic"
    with pytest.raises(ValueError, match="restic_archive_digest_mismatch"):
        restic_release.install_archive(archive, output)
    assert not output.exists()


def test_existing_binary_is_not_overwritten(tmp_path):
    output = tmp_path / "restic"
    output.write_bytes(b"existing-owned-by-user")
    with pytest.raises(ValueError, match="restic_output_must_be_new"):
        restic_release.install_archive(tmp_path / "missing", output)
    assert output.read_bytes() == b"existing-owned-by-user"


def test_modified_executable_is_refused_before_use(tmp_path):
    output = tmp_path / "restic"
    output.write_bytes(b"untrusted-executable")
    with pytest.raises(ValueError, match="restic_binary_digest_mismatch"):
        restic_release.verify_binary(output)


def test_packaged_model_preflight_uses_bundled_cases_without_sending(tmp_path):
    environment = {
        **os.environ, "MOONSHOT_API_KEY": "", "MODEL_NAME": "pilot-model",
        "MODEL_BASE_URL": "https://api.moonshot.cn/v1",
    }
    output = tmp_path / "model.json"
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "verify_real_model.py"),
         "--output", str(output)],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["sent_model_requests"] == 0
    assert "explicit_execute_flag_missing" in report["blockers"]
    assert "process_model_key_missing" in report["blockers"]
    assert "confirmed_exact_model_price_missing" in report["blockers"]


def test_inventory_uses_repo_path_without_dotenv_values(monkeypatch):
    root = SCRIPTS.parent
    calls = []

    def no_external_commands(command, cwd):
        calls.append(cwd)
        return 0, ""

    monkeypatch.setattr(verify_production_runtime, "captured", no_external_commands)
    report = verify_production_runtime.inventory(root)
    assert all(cwd == root for cwd in calls)
    assert report["uses_langgraph_dev"]
    assert report["local_dotenv_metadata"]["content_read"] is False
    assert report["docker_operations_started"] == 0
