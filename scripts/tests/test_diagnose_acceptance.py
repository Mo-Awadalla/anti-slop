import shutil
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anti_slop_core.diagnose import run_diagnose
from anti_slop_core.models import CheckSpec, CheckStatus, RunMode, RunSpec, ManifestStatus
from tests.helpers import LocalFixtureSandbox, tree_identity


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
    def setUp(self):
        for executable in ("true", "false"):
            if shutil.which(executable, path="/usr/bin:/bin") is None:
                self.skipTest(f"trusted fixture executable unavailable: {executable}")
        runner = patch("anti_slop_core.diagnose.BubblewrapSandbox", LocalFixtureSandbox)
        runner.start()
        self.addCleanup(runner.stop)

    def test_red_baseline_is_failed_not_fixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            make_repo(source)
            manifest, _, _ = run_diagnose(
                spec(source, root / "snapshot", CheckSpec("red", (shutil.which("false", path="/usr/bin:/bin"),))),
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
                    "flaky", (sys.executable, "-c", "from pathlib import Path; p=Path('.marker'); exists=p.exists(); p.touch(); raise SystemExit(int(exists))"), rerun=True,
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
                spec(source, root / "snapshot", CheckSpec("unit", (shutil.which("true", path="/usr/bin:/bin"),))),
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
            before = tree_identity(source)
            manifest, _, report_path = run_diagnose(
                spec(source, root / "snapshot", CheckSpec("unit", (shutil.which("true", path="/usr/bin:/bin"),))),
                hermes_home=str(root / "hermes"),
            )
            self.assertEqual(manifest.status, ManifestStatus.PASSED)
            self.assertIn("No edit is correct", report_path.read_text(encoding="utf-8"))
            self.assertEqual(tree_identity(source), before)

    def test_missing_sandbox_blocks_instead_of_running_on_host(self):
        from anti_slop_core.sandbox import SandboxUnavailable
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            make_repo(source)
            with patch("anti_slop_core.diagnose.BubblewrapSandbox", side_effect=SandboxUnavailable("fixture unavailable")):
                manifest, _, _ = run_diagnose(
                    spec(source, root / "snapshot", CheckSpec("unit", (shutil.which("true", path="/usr/bin:/bin"),))),
                    hermes_home=str(root / "hermes"),
                )
            self.assertEqual(manifest.status, ManifestStatus.BLOCKED)
            self.assertEqual(manifest.checks[0].status, CheckStatus.UNAVAILABLE)

    def test_no_checks_never_claims_verified_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            make_repo(source)
            manifest, _, _ = run_diagnose(spec(source, root / "snapshot"), hermes_home=str(root / "hermes"))
            self.assertNotEqual(manifest.status, ManifestStatus.PASSED)


if __name__ == "__main__":
    unittest.main()
