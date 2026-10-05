import subprocess
import tempfile
import unittest
from pathlib import Path

from anti_slop_core.adapters import select_adapter
from anti_slop_core.checkpoint import create_checkpoint
from anti_slop_core.findings import validate_findings
from anti_slop_core.models import (
    ArtifactRef,
    AttemptStatus,
    CheckRecord,
    CheckStatus,
    CommandAttempt,
    DiscoveryInfo,
    Finding,
    FindingSeverity,
    ManifestStatus,
    RunManifest,
    RunMode,
)
from anti_slop_core.report import render_report
from anti_slop_core.schema import SchemaError


class FindingAndReportTests(unittest.TestCase):
    def _manifest(self):
        artifact = ArtifactRef("checks/unit.stdout", "a" * 64, 0, "text/plain")
        stderr = ArtifactRef("checks/unit.stderr", "b" * 64, 0, "text/plain")
        attempt = CommandAttempt("unit", ("true",), ".", AttemptStatus.PASSED, 0, 1.0, artifact, stderr, True)
        check = CheckRecord("unit", CheckStatus.PASSED, (attempt,), ())
        return RunManifest(
            "run-test", RunMode.DIAGNOSE, "/repo", "/snapshot",
            ManifestStatus.PASSED, (check,), (), (artifact, stderr), DiscoveryInfo("/repo", "a" * 40, "main", False), None,
        )

    def test_vague_finding_action_is_rejected(self):
        manifest = self._manifest()
        finding = Finding(
            "f-1", "Complexity signal", "unit", ("checks/unit.stdout",),
            FindingSeverity.MEDIUM, "may increase change cost", 0.8,
            "clean this up", "could be intentional in this context",
        )
        with self.assertRaises(SchemaError):
            validate_findings(manifest, (finding,))

    def test_no_edit_report_is_explicit(self):
        report = render_report(self._manifest())
        self.assertIn("No edit is correct", report)
        self.assertIn("Evidence integrity", report)

    def test_asserted_pass_without_attempts_does_not_get_no_edit_endorsement(self):
        from dataclasses import replace
        manifest = self._manifest()
        manifest = replace(manifest, checks=(replace(manifest.checks[0], attempts=()),))
        self.assertNotIn("No edit is correct", render_report(manifest))

    def test_finding_cannot_cite_another_checks_capture(self):
        from dataclasses import replace
        manifest = self._manifest()
        other_ref = ArtifactRef("checks/other.stdout", "c" * 64, 0, "text/plain")
        manifest = replace(manifest, artifacts=manifest.artifacts + (other_ref,))
        finding = Finding("f-foreign", "Policy duplication", "unit", (other_ref.path,), FindingSeverity.LOW,
                          "Duplicated rules may drift", 0.7, "Compare the two discount branches against the contract", "Separate policies might be intentional")
        with self.assertRaises(SchemaError):
            validate_findings(manifest, (finding,))


class AdapterTests(unittest.TestCase):
    def test_unknown_repository_gets_reduced_generic_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = select_adapter(directory).summary()
            self.assertFalse(summary["supported"])
            self.assertFalse(summary["can_generate_findings"])
            self.assertFalse(summary["can_mutate"])


class CheckpointTests(unittest.TestCase):
    def test_isolated_checkpoint_restores_files_without_touching_git_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
            state = repo / "state.txt"
            state.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "state.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
            head_before = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

            checkpoint = create_checkpoint(str(repo))
            try:
                state.write_text("bad change\n", encoding="utf-8")
                checkpoint.rollback()
            finally:
                checkpoint.close()

            self.assertEqual(state.read_text(encoding="utf-8"), "before\n")
            self.assertEqual(
                subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
                head_before,
            )

    def test_failed_rollback_retains_usable_recovery_content_after_context_exit(self):
        import shutil
        from unittest.mock import patch
        from anti_slop_core.checkpoint import Checkpoint, CheckpointRecoveryError
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot"
            snapshot.mkdir()
            state = snapshot / "state.txt"
            state.write_text("recover this\n")
            checkpoint = Checkpoint.capture_snapshot(snapshot)
            self.addCleanup(shutil.rmtree, checkpoint.staging, ignore_errors=True)
            state.write_text("bad change\n")
            with patch("anti_slop_core.checkpoint._copy_contents", side_effect=OSError("restore denied")):
                with self.assertRaises(CheckpointRecoveryError) as caught:
                    with checkpoint:
                        checkpoint.rollback()
            checkpoint.close()
            self.assertTrue(checkpoint.staging.is_dir())
            self.assertEqual((checkpoint.staging / "state.txt").read_text(), "recover this\n")
            self.assertEqual(caught.exception.recovery_path, str(checkpoint.staging))
            self.assertIn("restore denied", caught.exception.reason)

    def test_successful_verified_rollback_removes_recovery_staging(self):
        from anti_slop_core.checkpoint import Checkpoint
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot"
            snapshot.mkdir()
            (snapshot / "state.txt").write_text("green\n")
            with Checkpoint.capture_snapshot(snapshot) as checkpoint:
                (snapshot / "state.txt").write_text("red\n")
                checkpoint.rollback()
                staging = checkpoint.staging
            self.assertEqual((snapshot / "state.txt").read_text(), "green\n")
            self.assertFalse(staging.exists())


if __name__ == "__main__":
    unittest.main()
