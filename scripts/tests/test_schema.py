import json
import unittest
from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

from anti_slop_core.models import (
    ArtifactRef,
    CheckRecord,
    CheckSpec,
    CommandAttempt,
    Finding,
    FindingSeverity,
    RunManifest,
    RunMode,
    RunSpec,
)
from anti_slop_core.schema import (
    SchemaError,
    load_artifact_ref,
    load_check_record,
    load_check_spec,
    load_command_attempt,
    load_finding,
    load_findings,
    load_run_manifest,
    load_run_spec,
)


class SchemaValidationTests(unittest.TestCase):
    def test_models_are_frozen_dataclasses(self):
        models = (
            RunSpec,
            CheckSpec,
            CommandAttempt,
            ArtifactRef,
            CheckRecord,
            Finding,
            RunManifest,
        )
        for model in models:
            with self.subTest(model=model.__name__):
                self.assertTrue(is_dataclass(model))
                self.assertTrue(model.__dataclass_params__.frozen)

    def test_load_run_spec_accepts_diagnose_contract(self):
        payload = {
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "mode": "diagnose",
            "checks": [
                {
                    "id": "unit",
                    "argv": ["python", "-m", "unittest"],
                    "cwd": ".",
                }
            ],
        }

        result = load_run_spec(json.dumps(payload))

        self.assertIsInstance(result, RunSpec)
        self.assertEqual(result.mode, RunMode.DIAGNOSE)
        self.assertEqual(result.checks[0].argv, ("python", "-m", "unittest"))

    def test_unknown_keys_are_rejected(self):
        payload = {
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "mode": "diagnose",
            "checks": [],
            "unexpected": True,
        }

        with self.assertRaises(SchemaError):
            load_run_spec(payload)

    def test_type_mismatches_are_rejected(self):
        payload = {
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "mode": "diagnose",
            "checks": "not-a-list",
        }

        with self.assertRaises(SchemaError):
            load_run_spec(payload)

    def test_relative_repo_paths_are_rejected(self):
        payload = {
            "repo_path": "relative/repo",
            "snapshot_root": "/workspace/snapshot",
            "mode": "diagnose",
            "checks": [],
        }

        with self.assertRaises(SchemaError):
            load_run_spec(payload)

    def test_p0_rejects_non_diagnose_mode(self):
        payload = {
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "mode": "refactor",
            "checks": [],
        }

        with self.assertRaises(SchemaError):
            load_run_spec(payload)

    def test_empty_argv_is_rejected(self):
        payload = {
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "mode": "diagnose",
            "checks": [{"id": "empty", "argv": [], "cwd": "."}],
        }

        with self.assertRaises(SchemaError):
            load_run_spec(payload)

    def test_duplicate_check_ids_are_rejected(self):
        check = {"id": "same", "argv": ["true"], "cwd": "."}
        payload = {
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "mode": "diagnose",
            "checks": [check, check.copy()],
        }

        with self.assertRaises(SchemaError):
            load_run_spec(payload)

    def test_cwd_must_stay_inside_snapshot_root(self):
        payload = {
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "mode": "diagnose",
            "checks": [{"id": "escape", "argv": ["true"], "cwd": "../outside"}],
        }

        with self.assertRaises(SchemaError):
            load_run_spec(payload)

    def test_shell_forms_are_rejected(self):
        for argv in (("sh", "-c", "true"), ("python", "-m", "x|y"), ("true", ">", "out"), ("echo", "$(id)")):
            with self.subTest(argv=argv):
                payload = {
                    "repo_path": "/workspace/repo",
                    "snapshot_root": "/workspace/snapshot",
                    "mode": "diagnose",
                    "checks": [{"id": "unsafe", "argv": list(argv), "cwd": "."}],
                }
                with self.assertRaises(SchemaError):
                    load_run_spec(payload)

    def test_shell_true_is_rejected(self):
        payload = {
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "mode": "diagnose",
            "checks": [
                {"id": "unsafe", "argv": ["true"], "cwd": ".", "shell": True}
            ],
        }

        with self.assertRaises(SchemaError):
            load_run_spec(payload)

    def test_invalid_manifest_status_is_rejected(self):
        payload = {
            "run_id": "run-1",
            "mode": "diagnose",
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "status": "invented",
            "checks": [],
            "findings": [],
        }

        with self.assertRaises(SchemaError):
            load_run_manifest(payload)

    def test_each_public_model_loader_validates_its_json_shape(self):
        snapshot = "/workspace/snapshot"
        check = {"id": "unit", "argv": ["true"], "cwd": "."}
        attempt = {
            "check_id": "unit",
            "argv": ["true"],
            "cwd": ".",
            "status": "passed",
        }
        finding = {
            "id": "finding-1",
            "check_id": "unit",
            "severity": "low",
            "message": "example",
        }

        self.assertIsInstance(load_check_spec(check, snapshot), CheckSpec)
        self.assertIsInstance(load_command_attempt(attempt, snapshot), CommandAttempt)
        self.assertIsInstance(load_artifact_ref({"path": "stdout.txt"}), ArtifactRef)
        self.assertIsInstance(
            load_check_record(
                {"check_id": "unit", "status": "passed", "attempts": [attempt]},
                snapshot,
            ),
            CheckRecord,
        )
        self.assertIsInstance(load_finding(finding), Finding)
        self.assertEqual(len(load_findings(json.dumps([finding]))), 1)

    def test_manifest_loader_builds_nested_frozen_models(self):
        payload = {
            "run_id": "run-1",
            "mode": "diagnose",
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "status": "passed",
            "checks": [
                {
                    "check_id": "unit",
                    "status": "passed",
                    "attempts": [
                        {
                            "check_id": "unit",
                            "argv": ["true"],
                            "cwd": ".",
                            "status": "passed",
                            "exit_code": 0,
                            "stdout_artifact": {"path": "checks/unit.stdout", "sha256": "a" * 64, "size_bytes": 0},
                            "stderr_artifact": {"path": "checks/unit.stderr", "sha256": "b" * 64, "size_bytes": 0},
                        }
                    ],
                    "finding_ids": [],
                }
            ],
            "findings": [],
            "artifacts": [
                {"path": "checks/unit.stdout", "sha256": "a" * 64, "size_bytes": 0},
                {"path": "checks/unit.stderr", "sha256": "b" * 64, "size_bytes": 0},
            ],
        }

        result = load_run_manifest(payload)

        self.assertIsInstance(result, RunManifest)
        self.assertIsInstance(result.checks[0], CheckRecord)
        self.assertIsInstance(result.checks[0].attempts[0], CommandAttempt)
        self.assertEqual(result.checks[0].attempts[0].exit_code, 0)
    def test_asserted_pass_status_is_rejected_when_checks_do_not_pass(self):
        payload = {
            "run_id": "run-1",
            "mode": "diagnose",
            "repo_path": "/workspace/repo",
            "snapshot_root": "/workspace/snapshot",
            "status": "passed",
            "checks": [{"check_id": "unit", "status": "failed", "attempts": []}],
            "findings": [],
            "artifacts": [],
        }

        with self.assertRaises(SchemaError):
            load_run_manifest(payload)


if __name__ == "__main__":
    unittest.main()
