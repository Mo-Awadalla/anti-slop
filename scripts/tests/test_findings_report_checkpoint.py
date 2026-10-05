import subprocess
import tempfile
import unittest
from pathlib import Path

from anti_slop_core.adapters import select_adapter
from anti_slop_core.checkpoint import create_checkpoint
from anti_slop_core.findings import validate_findings
from anti_slop_core.models import (
    ArtifactRef,
    CheckRecord,
    CheckStatus,
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
        check = CheckRecord("unit", CheckStatus.PASSED, (), ())
        return RunManifest(
            "run-test", RunMode.DIAGNOSE, "/repo", "/snapshot",
            ManifestStatus.PASSED, (check,), (), (artifact,), None, None,
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


if __name__ == "__main__":
    unittest.main()
