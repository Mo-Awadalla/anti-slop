import subprocess
import tempfile
import unittest
from pathlib import Path

from anti_slop_core.discovery import (
    clean_snapshot,
    discover,
    source_fingerprint,
)
from anti_slop_core.sandbox import Sandbox


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


class SandboxBoundaryTests(unittest.TestCase):
    def test_sandbox_command_contains_required_isolation_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            command = Sandbox(directory).argv(["/bin/true"])
            self.assertIn("--unshare-net", command)
            self.assertIn("--clearenv", command)
            self.assertIn("--tmpfs", command)
            self.assertIn("/workspace", command)
            bind_index = command.index("--bind")
            self.assertEqual(command[bind_index + 1], str(Path(directory).resolve()))
            self.assertEqual(command[bind_index + 2], "/workspace")
    def test_sandbox_cannot_read_host_file_outside_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            secret = Path(directory) / "host-secret"
            secret.write_text("private", encoding="utf-8")
            result = Sandbox(workspace).run(["/bin/sh", "-c", f"test ! -e {secret}"])
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_sandbox_network_namespace_has_no_reachable_external_route(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Sandbox(directory).run([
                "/usr/bin/python3", "-c",
                "import socket; s=socket.create_connection(('1.1.1.1', 80), 0.5)",
            ], timeout=5)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
