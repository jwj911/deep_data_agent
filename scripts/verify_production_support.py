"""Exercise support assets on public fixtures; optional real local restic I/O."""
from __future__ import annotations

import argparse
import io
import json
import os
import platform
import secrets
import stat
import subprocess
import tarfile
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import verify_backup_transport as backup
import verify_real_model as model
from restic_release import verify_binary
from verify_container_smoke import resolve_migration_head


def require(value, code):
    if not value:
        raise AssertionError(code)


def rejects(function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except Exception:
        return
    raise AssertionError("expected_rejection_missing")


def fixture(bundle, root, marker=b"public-synthetic-canary-20261028"):
    bundle.mkdir()
    (bundle / "mysql.sql").write_bytes(b"-- synthetic, no business data\nSELECT 1;\n")
    for name in ("langgraph.tar", "managed-files.tar"):
        with tarfile.open(bundle / name, "w") as archive:
            entry = tarfile.TarInfo("canary.json")
            entry.size = len(marker)
            archive.addfile(entry, io.BytesIO(marker))
    manifest = {
        "format": 1, "quiesced": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "revision": resolve_migration_head(root),
        "lock_sha256": backup.digest(root / "requirements.txt"),
        "runtime": {"source_sha256": backup.source_fingerprint(root)},
        "artifacts": {
            name: {
                "size": (bundle / name).stat().st_size,
                "sha256": backup.digest(bundle / name),
            }
            for name in ("mysql.sql", "langgraph.tar", "managed-files.tar")
        },
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return backup.digest(bundle / "manifest.json")


def support_checks(root, temporary):
    passed = []
    suite, corpus_sha = model.load_cases(Path(model.__file__).with_name("model-eval-cases.json"))
    for case in suite["cases"]:
        require(model.matches(case["expected"], model.reference(case)), case["id"])
        passed.append("reference_" + case["id"])
    require(model.matches({"sum": 20}, {"sum": Decimal("20.00")}), "decimal_equivalence")
    rejects(model.decimal, True)
    rejects(model.decimal, "NaN")
    rejects(model.parse_answer, '{"sum": 10, "sum": 999}')
    rejects(model.parse_answer, '{"sum": NaN}')
    require(not model.matches({"sum": "999"}, {"sum": Decimal("10")}), "incorrect_numeric")
    require(not model.matches({"count": True}, {"count": 1}), "bool_count")
    require(not model.matches({"sum": 10, "secret": "extra"}, {"sum": Decimal("10")}), "extra_key")
    passed.extend([
        "decimal_equivalence", "bool_and_nonfinite_rejection", "duplicate_json_key_rejection",
        "incorrect_reference_rejection", "extra_fields_rejection",
    ])
    rejects(model.extract_usage, {"usage": {
        "prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 4,
    }})
    rejects(model.extract_usage, {"usage": {
        "prompt_tokens": True, "completion_tokens": 0, "total_tokens": 1,
    }})
    passed.append("usage_truth_validation")
    args = argparse.Namespace(execute=True, price_file=None, max_cny="1")
    with patch.dict(os.environ, {}, clear=True), patch.object(model, "post_completion") as sender:
        report, code = model.evaluate(args, suite, corpus_sha)
        require(code == 2 and report["sent_model_requests"] == 0, "preflight_zero_calls")
        sender.assert_not_called()
    passed.append("missing_key_and_price_zero_calls")
    prices = {
        "input_per_mtok": "6.5", "output_per_mtok": "27",
        "cached_input_per_mtok": "1.1",
    }
    require(model.upper_cost(suite["cases"], prices) > 0, "positive_cost_bound")
    require(
        model.tariff_cost(
            {"prompt_tokens": 100, "completion_tokens": 10, "cached_tokens": 40}, prices,
        ) == Decimal("0.000704"),
        "cached_cost_reference",
    )
    passed.append("tariff_and_cache_reference")
    price_path = temporary / "price.json"
    price_path.write_text(json.dumps({
        **prices, "model": "pilot-model", "currency": "CNY",
        "source_url": "https://platform.kimi.com/docs/pricing/chat",
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }), encoding="utf-8")
    args.price_file = price_path
    with patch.dict(os.environ, {
        "MOONSHOT_API_KEY": "synthetic-not-a-real-key", "MODEL_NAME": "pilot-model",
    }, clear=True), patch.object(model, "post_completion") as sender:
        args.max_cny = "0.000001"
        report, code = model.evaluate(args, suite, corpus_sha)
        require(code == 2 and "preflight_fee_cap_exceeded" in report["blockers"], "fee_cap")
        sender.assert_not_called()
        args.max_cny = "1"
        sender.side_effect = lambda *_args: {
            "model": "pilot-model",
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(suite["cases"][sender.call_count - 1]["expected"])},
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
        }
        report, code = model.evaluate(args, suite, corpus_sha)
        require(code == 0 and report["sent_model_requests"] == 5, "bounded_five_requests")
        require(report["production_effect_gate"] == "not_evaluated", "no_scope_promotion")
        sender.reset_mock()
        sender.side_effect = TimeoutError()
        report, code = model.evaluate(args, suite, corpus_sha)
        require(code == 1 and sender.call_count == 5 and report["client_retries"] == 0, "no_retry")
    passed.extend(["fee_cap_before_send", "bounded_pilot_orchestration", "timeout_no_retry"])
    with patch.dict(os.environ, {"RESTIC_REPOSITORY": "s3:http://example.invalid/test"}, clear=True):
        require(not backup.remote_configuration(), "http_repo")
    with patch.dict(os.environ, {
        "RESTIC_REPOSITORY": "s3:https://user:pass@example.invalid/test",
    }, clear=True):
        require(not backup.remote_configuration(), "userinfo_repo")
    with patch.dict(os.environ, {
        "RESTIC_REPOSITORY": "s3:https://example.invalid/test",
        "RESTIC_REPOSITORY_FILE": "override",
    }, clear=True):
        require(not backup.remote_configuration(), "repo_override")
    passed.append("transport_origin_and_override_rejection")
    bundle = temporary / "bundle"
    manifest_sha = fixture(bundle, root)
    backup.validate(bundle, root, manifest_sha, recent=True)
    passed.append("synthetic_bundle_positive_validation")
    rejects(backup.validate, bundle, root, "0" * 64)
    passed.append("manifest_anchor_rejection")
    (bundle / "unrelated.txt").write_text("public unrelated fixture", encoding="utf-8")
    rejects(backup.validate, bundle, root, manifest_sha)
    (bundle / "unrelated.txt").unlink()
    passed.append("extra_staging_file_rejection")
    sql = (bundle / "mysql.sql").read_bytes()
    (bundle / "mysql.sql").write_bytes(sql + b"tamper")
    rejects(backup.validate, bundle, root, manifest_sha)
    (bundle / "mysql.sql").write_bytes(sql)
    passed.append("artifact_tampering_rejection")
    manifest_path = bundle / "manifest.json"
    original = manifest_path.read_bytes()
    changed = json.loads(original)
    changed["runtime"]["source_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(changed), encoding="utf-8")
    rejects(backup.validate, bundle, root, backup.digest(manifest_path))
    manifest_path.write_bytes(original)
    passed.append("source_fingerprint_rejection")
    return passed, suite, bundle, manifest_sha


def verify_pack_corruption(pack, invoke):
    """Mutate only this synthetic repository pack and always restore its mode."""
    original = pack.read_bytes()
    original_mode = stat.S_IMODE(pack.stat().st_mode)
    corrupted = bytearray(original)
    corrupted[len(corrupted) // 2] ^= 1
    # restic creates read-only packs on Linux. This is a deliberate corruption
    # fixture, not a change to the transport helper or a deployed repository.
    pack.chmod(original_mode | stat.S_IWUSR)
    try:
        pack.write_bytes(corrupted)
        invoke("check", "--read-data", success=False)
    finally:
        try:
            pack.write_bytes(original)
        finally:
            pack.chmod(original_mode)
    invoke("check", "--read-data")
    return {
        "original_pack_mode": oct(original_mode),
        "restored_pack_mode": oct(stat.S_IMODE(pack.stat().st_mode)),
        "restored_bytes": pack.read_bytes() == original,
    }


def restic_checks(executable, root, temporary, bundle, manifest_sha):
    binary = verify_binary(executable)
    repository = temporary / "encrypted-repository"
    environment = {
        name: os.environ[name] for name in ("PATH", "SystemRoot", "WINDIR")
        if name in os.environ
    }
    environment.update(
        RESTIC_REPOSITORY=str(repository), RESTIC_PASSWORD=secrets.token_urlsafe(32),
        TMP=str(temporary), TEMP=str(temporary), TMPDIR=str(temporary),
    )

    def invoke(*arguments, success=True, password=None, cwd=None):
        child = dict(environment)
        if password is not None:
            child["RESTIC_PASSWORD"] = password
        result = subprocess.run(
            [str(executable), "--no-cache", "--json", *arguments],
            cwd=cwd, env=child, capture_output=True, timeout=45,
        )
        require((result.returncode == 0) == success, "restic_exit_contract")
        return result.stdout

    version = subprocess.run(
        [str(executable), "version"], capture_output=True, text=True, timeout=10,
    )
    require(version.returncode == 0, "restic_version")
    invoke("init", "--repository-version", "2")
    passed = ["local_encrypted_repository_init"]
    names = ("mysql.sql", "langgraph.tar", "managed-files.tar", "manifest.json")
    snapshots = []
    for index in range(3):
        raw = invoke(
            "backup", "--host", "deep-data-agent", "--tag",
            "dda-format1" if index < 2 else "unrelated",
            *names, cwd=bundle,
        )
        summary = next(
            json.loads(line) for line in raw.splitlines()
            if json.loads(line).get("message_type") == "summary"
        )
        snapshots.append(summary["snapshot_id"])
    require(len(set(snapshots)) == 3, "three_snapshot_identities")
    passed.append("three_real_local_snapshot_writes")
    invoke("check", "--read-data")
    passed.append("full_data_integrity_check")
    invoke("snapshots", password=secrets.token_urlsafe(32), success=False)
    passed.append("wrong_password_rejected")
    marker = b"public-synthetic-canary-20261028"
    require(all(
        marker not in path.read_bytes()
        for path in repository.rglob("*") if path.is_file()
    ), "plaintext_not_in_repository")
    passed.append("synthetic_plaintext_absent_from_repository")
    before = {row["id"] for row in json.loads(invoke("snapshots"))}
    plan = json.loads(invoke(
        "forget", "--dry-run", "--tag", "dda-format1",
        "--group-by", "host,tags", "--keep-last", "1",
    ))
    after = {row["id"] for row in json.loads(invoke("snapshots"))}
    require(before == after, "retention_dry_run_preserves_snapshots")
    removed = {row["id"] for group in plan for row in group.get("remove", [])}
    require(len(removed) == 1 and snapshots[2] not in removed, "retention_tag_scope")
    passed.append("retention_dry_run_and_unrelated_tag_preservation")
    original_runner = backup.run_restic

    def isolated_runner(restic, arguments, **kwargs):
        return original_runner(restic, arguments, environment=environment, **kwargs)

    with patch.object(backup, "run_restic", side_effect=isolated_runner):
        target = temporary / "downloaded"
        start = time.monotonic()
        restored, _ = backup.retrieve(
            executable, snapshots[1], target, root, manifest_sha, temporary,
        )
        latency = time.monotonic() - start
        require(
            all(backup.digest(restored / name) == backup.digest(bundle / name) for name in names),
            "all_four_files_roundtrip",
        )
        rejects(
            backup.retrieve, executable, snapshots[1], target, root, manifest_sha, temporary,
        )
        rejects(
            backup.retrieve, executable, snapshots[1], temporary / "too-large",
            root, manifest_sha, temporary, 1,
        )
    passed.extend(["four_file_hash_roundtrip", "nonempty_target_rejection", "restore_byte_cap"])
    packs = [path for path in (repository / "data").rglob("*") if path.is_file()]
    require(bool(packs), "encrypted_pack_exists")
    ciphertext_control = verify_pack_corruption(packs[0], invoke)
    passed.append("ciphertext_tampering_detected_and_clean_recheck")
    return {
        "outcome": "passed", "checks": passed,
        "version": version.stdout.strip(),
        "binary_verification": binary,
        "ciphertext_control": ciphertext_control,
        "executable_sha256": backup.digest(executable),
        "restore_seconds": round(latency, 6),
        "scope": "public_fixture_local_filesystem_repository",
        "offsite_gate": "not_evaluated", "production_recovery_gate": "not_evaluated",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--restic", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir() or not args.work_dir.is_dir():
        parser.error("existing work directory and new output file required")
    report = {
        "format": 1, "recorded_at": datetime.now(timezone.utc).isoformat(),
        "gate": "production_support_assets",
        "scope": "offline_orchestration_and_optional_local_encryption_only",
        "production_decision": "NO-GO",
        "platform": platform.system(),
    }
    code = 0
    try:
        with backup.temporary_directory(args.work_dir, "support-check-") as directory:
            temporary = Path(directory)
            passed, _, bundle, manifest_sha = support_checks(args.repo_root, temporary)
            report["offline_checks"] = passed
            report["offline_outcome"] = "passed"
            if args.restic is not None and args.restic.is_file():
                report["local_restic"] = restic_checks(
                    args.restic, args.repo_root, temporary, bundle, manifest_sha,
                )
            else:
                report["local_restic"] = {
                    "outcome": "blocked", "code": "verified_restic_executable_unavailable",
                    "offsite_gate": "not_evaluated",
                }
    except Exception as exc:
        report["failure"] = type(exc).__name__
        if isinstance(exc, backup.TransportError):
            report["failure_code"] = str(exc)
        if isinstance(exc, AssertionError):
            report["assertion"] = str(exc)
        report["outcome"] = "failed"
        code = 1
    report.setdefault("outcome", "passed")
    model.save(args.output, report)
    print(json.dumps({
        "outcome": report["outcome"], "offline_checks": len(report.get("offline_checks", [])),
        "local_restic_outcome": report.get("local_restic", {}).get("outcome"),
        "production_decision": "NO-GO", "failure": report.get("failure"),
        "failure_code": report.get("failure_code"),
    }))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
