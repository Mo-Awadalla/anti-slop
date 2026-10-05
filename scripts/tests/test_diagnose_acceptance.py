import subprocess
import tempfile
import unittest
from pathlib import Path

from anti_slop_core.diagnose import run_diagnose
from anti_slop_core.models import CheckSpec, CheckStatus, RunMode, RunSpec, ManifestStatus


def make_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "test"], check=True)
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)


def spec(source: Path, snapshot: Path, *checks: CheckSpec) -> RunSpec:
    return RunSpec(str(source), str(snapshot), RunMode.DIAGNOSE, tuple(checks))


class DiagnoseAcceptanceTests(unittest.TestCase):
    def test_red_baseline_is_failed_not_fixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            make_repo(source)
            manifest, _, _ = run_diagnose(
                spec(source, root / "snapshot", CheckSpec("red", ("/bin/false",))),
                hermes_home=str(root / "hermes"),
            )
            self.assertEqual(manifest.checks[0].status, CheckStatus.FAILED)
            self.assertNotEqual(manifest.status, ManifestStatus.PASSED)

    def test_missing_runner_is_unavailable_and_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            make_repo(source)
            manifest, _, _ = run_diagnose(
                spec(source, root / "snapshot", CheckSpec("missing", ("/no/such/executable",))),
                hermes_home=str(root / "hermes"),
            )
            self.assertEqual(manifest.checks[0].status, CheckStatus.UNAVAILABLE)
            self.assertNotEqual(manifest.status, ManifestStatus.PASSED)

    def test_flaky_rerun_stops_clean_pass_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            make_repo(source)
            manifest, _, _ = run_diagnose(
                spec(source, root / "snapshot", CheckSpec(
                    "flaky", ("/bin/sh", "-c", "if test -e .marker; then exit 1; else touch .marker; exit 0; fi"), rerun=True,
                )),
                hermes_home=str(root / "hermes"),
            )
            self.assertEqual(manifest.checks[0].status, CheckStatus.FLAKY)
            self.assertNotEqual(manifest.status, ManifestStatus.PASSED)

    def test_dirty_source_stops_before_checks_and_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            make_repo(source)
            (source / "README.md").write_text("dirty\n", encoding="utf-8")
            before = (source / "README.md").read_text(encoding="utf-8")
            manifest, _, _ = run_diagnose(
                spec(source, root / "snapshot", CheckSpec("unit", ("/bin/true",))),
                hermes_home=str(root / "hermes"),
            )
            self.assertEqual(manifest.status, ManifestStatus.STOPPED)
            self.assertEqual(manifest.checks, ())
            self.assertEqual((source / "README.md").read_text(encoding="utf-8"), before)

    def test_success_does_not_modify_source_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            make_repo(source)
            before = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True)
            head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True)
            manifest, _, report_path = run_diagnose(
                spec(source, root / "snapshot", CheckSpec("unit", ("/bin/true",))),
                hermes_home=str(root / "hermes"),
            )
            self.assertEqual(manifest.status, ManifestStatus.PASSED)
            self.assertIn("No edit is correct", report_path.read_text(encoding="utf-8"))
            self.assertEqual(subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True), before)
            self.assertEqual(subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True), head)


if __name__ == "__main__":
    unittest.main()
