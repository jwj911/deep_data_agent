"""Regression drill against a real encrypted local repository and synthetic data."""
from __future__ import annotations

import argparse
import faulthandler
import json
import os
import platform
import secrets
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import verify_backup_transport as transport
from restic_release import verify_binary
from verify_production_support import fixture


class RecoveryAdmission(unittest.TestCase):
    root: Path
    work: Path
    restic: Path

    @classmethod
    def setUpClass(cls):
        cls.temporary = transport.temporary_directory(cls.work, "admission-")
        cls.directory = cls.temporary.__enter__()
        cls.environment = {
            name: value for name, value in os.environ.items()
            if not name.startswith(("RESTIC_", "AWS_"))
        }
        cls.environment.update(
            RESTIC_REPOSITORY=str(cls.directory / "repository"),
            RESTIC_PASSWORD=secrets.token_urlsafe(32),
            TMP=str(cls.directory), TEMP=str(cls.directory), TMPDIR=str(cls.directory),
        )
        try:
            cls.invoke("init", "--repository-version", "2")
            cls.source = cls.directory / "source"
            cls.source.mkdir()
            cls.bundle = cls.source / "bundle"
            cls.manifest_sha = fixture(cls.bundle, cls.root)
            cls.valid_snapshot = cls.snapshot("bundle")
            (cls.source / "unrelated.txt").write_bytes(b"public unrelated fixture")
            cls.extra_snapshot = cls.snapshot("bundle", "unrelated.txt")
        except BaseException:
            cls.temporary.__exit__(*sys.exc_info())
            raise

    @classmethod
    def tearDownClass(cls):
        cls.temporary.__exit__(None, None, None)

    @classmethod
    def invoke(cls, *args):
        result = subprocess.run(
            [str(cls.restic), "--no-cache", "--json", *args],
            cwd=getattr(cls, "source", cls.directory), env=cls.environment,
            capture_output=True, timeout=45,
        )
        if result.returncode:
            raise RuntimeError(f"local_restic_exit_{result.returncode}")
        return result.stdout

    @classmethod
    def snapshot(cls, *paths):
        raw = cls.invoke("backup", "--host", "admission-fixture", *paths)
        summaries = [
            row for line in raw.splitlines()
            if (row := json.loads(line)).get("message_type") == "summary"
        ]
        return summaries[0]["snapshot_id"]

    def setUp(self):
        self.target = self.directory / self._testMethodName
        runner = transport.run_restic

        def isolated(restic, args, **kwargs):
            return runner(restic, args, environment=self.environment, **kwargs)

        self.mock = patch.object(transport, "run_restic", side_effect=isolated)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def retrieve(self, *, snapshot=None, manifest_sha=None, max_bytes=1024 ** 3):
        return transport.retrieve(
            self.restic, snapshot or self.valid_snapshot, self.target, self.root,
            self.manifest_sha if manifest_sha is None else manifest_sha,
            self.directory, max_bytes,
        )

    def test_valid_snapshot_roundtrip(self):
        restored, _ = self.retrieve()
        for name in ("mysql.sql", "langgraph.tar", "managed-files.tar", "manifest.json"):
            self.assertEqual(
                transport.digest(restored / name), transport.digest(self.bundle / name),
            )

    def test_wrong_manifest_leaves_target_absent(self):
        with self.assertRaisesRegex(transport.TransportError, "manifest_hash_mismatch"):
            self.retrieve(manifest_sha="0" * 64)
        self.assertFalse(self.target.exists(), "invalid bundle wrote the final target")

    def test_unrelated_snapshot_file_refused_without_target(self):
        with self.assertRaisesRegex(transport.TransportError, "snapshot_file_set_invalid"):
            self.retrieve(snapshot=self.extra_snapshot)
        self.assertFalse(self.target.exists(), "unrelated snapshot entry was restored")

    def test_oversized_snapshot_leaves_target_absent(self):
        with self.assertRaisesRegex(transport.TransportError, "snapshot_size_unknown_or_exceeded"):
            self.retrieve(max_bytes=1)
        self.assertFalse(self.target.exists())

    def test_occupied_target_untouched(self):
        self.target.mkdir()
        sentinel = self.target / "sentinel"
        sentinel.write_bytes(b"owner-data")
        with self.assertRaisesRegex(transport.TransportError, "retrieve_target_must_be_new"):
            self.retrieve()
        self.assertEqual(sentinel.read_bytes(), b"owner-data")
        self.assertEqual(list(self.target.iterdir()), [sentinel])

    def test_missing_anchor_does_not_contact_repository(self):
        with patch.object(transport, "run_restic") as command:
            with self.assertRaisesRegex(transport.TransportError, "authoritative_manifest_hash_required"):
                self.retrieve(manifest_sha="")
            command.assert_not_called()
        self.assertFalse(self.target.exists())

    def test_download_failure_cleans_staging(self):
        original = transport.run_restic

        def interrupt(restic, args, **kwargs):
            if args[0] == "dump" and args[-1].endswith("/langgraph.tar"):
                kwargs["output_file"].write(b"interrupted fixture")
                raise transport.TransportError("injected_download_failure")
            return original(restic, args, **kwargs)

        before = set(self.directory.iterdir())
        with patch.object(transport, "run_restic", side_effect=interrupt):
            with self.assertRaisesRegex(transport.TransportError, "injected_download_failure"):
                self.retrieve()
        self.assertFalse(self.target.exists())
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_corrupt_download_does_not_publish_target(self):
        original = transport.run_restic

        def corrupt(restic, args, **kwargs):
            if args[0] == "dump" and args[-1].endswith("/mysql.sql"):
                kwargs["output_file"].write(b"x" * (self.bundle / "mysql.sql").stat().st_size)
                return b""
            return original(restic, args, **kwargs)

        before = set(self.directory.iterdir())
        with patch.object(transport, "run_restic", side_effect=corrupt):
            with self.assertRaisesRegex(Exception, "^recovery_bundle_invalid$"):
                self.retrieve()
        self.assertFalse(self.target.exists())
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_snapshot_summary_cannot_hide_file_bytes(self):
        original = transport.run_restic

        def underreport(restic, args, **kwargs):
            raw = original(restic, args, **kwargs)
            if args[0] == "snapshots":
                data = json.loads(raw)
                data[0]["summary"]["total_bytes_processed"] = 1
                return json.dumps(data).encode()
            return raw

        with patch.object(transport, "run_restic", side_effect=underreport):
            with self.assertRaisesRegex(transport.TransportError, "snapshot_file_size_invalid"):
                self.retrieve(max_bytes=100)
        self.assertFalse(self.target.exists())

    def test_concurrent_target_creation_is_not_overwritten(self):
        original = transport._promote

        def race(source, target):
            target.mkdir()
            original(source, target)

        with patch.object(transport, "_promote", side_effect=race):
            with self.assertRaises((OSError, transport.TransportError)):
                self.retrieve()
        self.assertTrue(self.target.is_dir())
        self.assertEqual(list(self.target.iterdir()), [])

    def test_subprocess_output_limit_is_enforced(self):
        with self.assertRaisesRegex(transport.TransportError, "restic_output_limit_or_write_failure"):
            transport.run_restic(
                self.restic, ["ls", self.valid_snapshot], work_dir=self.directory,
                max_output_bytes=1,
            )

    def test_subprocess_deadline_is_enforced(self):
        with self.assertRaisesRegex(transport.TransportError, "restic_command_timeout"):
            transport.run_restic(
                self.restic, ["snapshots"], work_dir=self.directory, timeout_seconds=0.000001,
            )

    def test_staging_permission_failure_is_not_retried(self):
        with patch.object(Path, "mkdir", side_effect=PermissionError()) as creation:
            with self.assertRaisesRegex(transport.TransportError, "private_staging_creation_failed"):
                with transport.temporary_directory(self.directory, "denied-"):
                    self.fail("permission failure was ignored")
            self.assertEqual(creation.call_count, 1)

    def test_staging_name_collisions_are_bounded(self):
        with patch.object(Path, "mkdir", side_effect=FileExistsError()) as creation:
            with self.assertRaisesRegex(transport.TransportError, "private_staging_name_collisions"):
                with transport.temporary_directory(self.directory, "collision-"):
                    self.fail("name collision was ignored")
            self.assertEqual(creation.call_count, 8)

    def test_local_manifest_limit_precedes_content_read(self):
        with transport.temporary_directory(self.directory, "oversize-manifest-") as bundle:
            (bundle / "manifest.json").write_bytes(b" " * (64 * 1024 + 1))
            with patch.object(transport, "digest") as content_read:
                with self.assertRaisesRegex(transport.TransportError, "manifest_size_invalid"):
                    transport.validate(bundle, self.root, "0" * 64)
                content_read.assert_not_called()


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed_tests = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed_tests.append(test._testMethodName)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--restic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir() or not args.work_dir.is_dir():
        parser.error("existing private work directory and new output file required")
    binary = verify_binary(args.restic)
    before = set(args.work_dir.iterdir())
    started = time.monotonic()
    RecoveryAdmission.root = args.repo_root
    RecoveryAdmission.work = args.work_dir
    RecoveryAdmission.restic = args.restic
    faulthandler.dump_traceback_later(90, exit=True)
    result = unittest.TextTestRunner(
        stream=sys.stderr, verbosity=2, resultclass=EvidenceResult,
    ).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryAdmission),
    )
    faulthandler.cancel_dump_traceback_later()
    report = {
        "gate": "recovery_admission_regression",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "outcome": "passed" if result.wasSuccessful() else "failed",
        "tests_run": result.testsRun,
        "passed_tests": result.passed_tests,
        "platform": platform.system(),
        "atomic_publish": "renameat2_RENAME_NOREPLACE" if sys.platform == "linux" else "Windows_rename",
        "binary_verification": binary,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "work_directory_cleaned": set(args.work_dir.iterdir()) == before,
        "failed_tests": [str(test) for test, _ in result.failures],
        "errors": [str(test) for test, _ in result.errors],
        "scope": "public_synthetic_local_restic",
        "production_decision": "NO-GO",
    }
    if not report["work_directory_cleaned"]:
        report["outcome"] = "failed"
    transport.save(args.output, report)
    print(json.dumps(report))
    return 0 if report["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
