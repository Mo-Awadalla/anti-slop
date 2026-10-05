import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anti_slop_core.discovery import (
    clean_snapshot,
    discover,
    source_fingerprint,
)
from anti_slop_core.sandbox import Sandbox, SandboxUnavailable


def make_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "test"], check=True)
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)


class DiscoveryAcceptanceTests(unittest.TestCase):
    def test_discovery_records_clean_state_and_snapshot_does_not_modify_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            make_repo(source)
            before = source_fingerprint(source)
            info = discover(source)
            self.assertFalse(info.dirty)
            snapshot = clean_snapshot(source, Path(directory) / "snapshot")
            self.assertTrue((snapshot / "README.md").exists())
            self.assertEqual(before, source_fingerprint(source))

    def test_dirty_source_is_visible_before_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            make_repo(source)
            (source / "README.md").write_text("changed\n", encoding="utf-8")
            self.assertTrue(discover(source).dirty)

    def test_source_fingerprint_detects_permission_and_revision_identity_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            make_repo(source)
            before = source_fingerprint(source)
            (source / "README.md").chmod(0o755)
            self.assertNotEqual(source_fingerprint(source), before)
            (source / "README.md").chmod(0o644)
            self.assertEqual(source_fingerprint(source), before)
            subprocess.run(["git", "-C", str(source), "checkout", "-qb", "identity-change"], check=True)
            self.assertNotEqual(source_fingerprint(source), before)


class SandboxBoundaryTests(unittest.TestCase):
    def test_sandbox_command_contains_required_isolation_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("anti_slop_core.sandbox.shutil.which", return_value="/usr/bin/bwrap"):
                command = Sandbox(directory).argv(["/bin/true"])
            self.assertIn("--unshare-net", command)
            self.assertIn("--clearenv", command)
            self.assertIn("--tmpfs", command)
            self.assertIn("/workspace", command)
            bind_index = command.index("--bind")
            self.assertEqual(command[bind_index + 1], str(Path(directory).resolve()))
            self.assertEqual(command[bind_index + 2], "/workspace")

    def test_absolute_cwd_maps_inside_workspace_and_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            subdir = workspace / "subdir"
            subdir.mkdir(parents=True)
            outside = Path(directory) / "outside"
            outside.mkdir()
            (workspace / "escape").symlink_to(outside, target_is_directory=True)
            with patch("anti_slop_core.sandbox.shutil.which", return_value="/usr/bin/bwrap"):
                sandbox = Sandbox(workspace)
                command = sandbox.argv(["/bin/true"], str(subdir))
                self.assertEqual(command[command.index("--chdir") + 1], "/workspace/subdir")
                for cwd in ("../outside", "escape", str(outside)):
                    with self.subTest(cwd=cwd), self.assertRaises(ValueError):
                        sandbox.argv(["/bin/true"], cwd)

    def test_unspecified_timeout_still_has_a_finite_execution_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("anti_slop_core.sandbox.shutil.which", return_value="/usr/bin/bwrap"), patch("anti_slop_core.sandbox.subprocess.run", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as process:
                Sandbox(directory).run(["/bin/true"], timeout=None)
            self.assertGreater(process.call_args.kwargs["timeout"], 0)
            self.assertLessEqual(process.call_args.kwargs["timeout"], 300)

    def test_bubblewrap_startup_failure_is_unavailable_not_a_project_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.CompletedProcess([], 1, b"", b"bwrap: loopback: Failed to create NETLINK_ROUTE socket: Operation not permitted\n")
            with patch("anti_slop_core.sandbox.shutil.which", return_value="/usr/bin/bwrap"), patch("anti_slop_core.sandbox.subprocess.run", return_value=result):
                with self.assertRaises(SandboxUnavailable):
                    Sandbox(directory).run(["/bin/true"])
    def test_sandbox_cannot_read_host_file_outside_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            secret = Path(directory) / "host-secret"
            secret.write_text("private", encoding="utf-8")
            sandbox = self._operational_sandbox(workspace)
            result = sandbox.run(["/usr/bin/python3", "-c", "import os,sys; sys.exit(int(os.path.exists(sys.argv[1])))", str(secret)])
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_sandbox_network_namespace_has_no_reachable_external_route(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self._operational_sandbox(directory).run([
                "/usr/bin/python3", "-c",
                "import errno,socket; s=socket.socket(); result=s.connect_ex(('1.1.1.1',80)); assert result in (errno.ENETUNREACH,errno.EHOSTUNREACH),result; print('isolated')",
            ], timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            self.assertEqual(result.stdout.strip(), b"isolated")

    def _operational_sandbox(self, workspace):
        try:
            sandbox = Sandbox(workspace)
            result = sandbox.run(["/bin/true"], timeout=5)
        except SandboxUnavailable as exc:
            self.skipTest(f"real Bubblewrap unavailable: {exc}")
        if result.returncode != 0:
            self.skipTest(f"real Bubblewrap probe failed (exit {result.returncode}): {result.stderr.decode(errors='replace').strip()}")
        return sandbox


if __name__ == "__main__":
    unittest.main()
