import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anti_slop_core.discovery import (
    DirtySourceError,
    DiscoveryError,
    create_snapshot,
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

    def test_snapshot_excludes_ignored_secrets_but_keeps_tracked_ignored_names(self):
        import anti_slop_core.discovery as discovery_module
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            make_repo(source)
            (source / ".gitignore").write_text(".env\nprivate/\ntracked secret*\n")
            tracked_name = "tracked secret\nname.txt"
            (source / tracked_name).write_text("tracked revision bytes\n")
            subprocess.run(["git", "-C", str(source), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(source), "add", "-f", "--", tracked_name], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-qm", "tracked ignored fixture"], check=True)
            (source / ".env").write_text("TOKEN=must-not-enter-snapshot\n")
            (source / "private").mkdir()
            (source / "private/README.md").write_text("python3 leak.py\n")
            (source / "private/host-link").symlink_to("/etc/passwd")
            before = source_fingerprint(source)
            opened = []
            original_open = discovery_module._open_tracked

            def recording_open(root, relative):
                opened.append(relative)
                return original_open(root, relative)

            with patch.object(discovery_module, "_open_tracked", side_effect=recording_open):
                snapshot = clean_snapshot(source, Path(directory) / "snapshot")
                self.assertEqual(source_fingerprint(source), before)
            self.assertNotIn(".env", opened)
            self.assertFalse(any(path.startswith("private/") for path in opened))
            self.assertFalse((snapshot / ".env").exists())
            self.assertFalse((snapshot / "private").exists())
            self.assertFalse((snapshot / ".git").exists())
            self.assertEqual((snapshot / tracked_name).read_bytes(), b"tracked revision bytes\n")
            self.assertNotIn("python3", " ".join(discover(source).candidates))
            (source / ".env").write_text("TOKEN=changed-secret\n")
            self.assertEqual(source_fingerprint(source), before)

    def test_untracked_dirty_content_never_enters_a_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            make_repo(source)
            (source / "untracked.txt").write_text("private draft\n")
            target = Path(directory) / "snapshot"
            with self.assertRaises(DirtySourceError):
                clean_snapshot(source, target)
            self.assertFalse(target.exists())
            self.assertEqual((source / "untracked.txt").read_text(), "private draft\n")

    def test_revision_race_removes_only_the_disposable_copy(self):
        import anti_slop_core.discovery as discovery_module
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            make_repo(source)
            info = discover(source)
            copy = discovery_module.shutil.copyfileobj

            def switching_copy(*args, **kwargs):
                copy(*args, **kwargs)
                subprocess.run(["git", "-C", str(source), "checkout", "-qb", "changed-during-copy"], check=True)

            target = Path(directory) / "snapshot"
            with patch.object(discovery_module.shutil, "copyfileobj", side_effect=switching_copy):
                with self.assertRaises(DirtySourceError):
                    create_snapshot(info, target)
            self.assertFalse(target.exists())
            self.assertEqual((source / "README.md").read_text(), "fixture\n")

    def test_stale_head_and_new_dirty_content_abort_snapshot(self):
        import anti_slop_core.discovery as discovery_module
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            make_repo(source)
            stale = discover(source)
            subprocess.run(["git", "-C", str(source), "commit", "--allow-empty", "-qm", "new head"], check=True)
            target = Path(directory) / "snapshot"
            with self.assertRaises(DirtySourceError):
                create_snapshot(stale, target)
            self.assertFalse(target.exists())
            fresh = discover(source)
            copy = discovery_module.shutil.copyfileobj

            def dirtying_copy(*args, **kwargs):
                copy(*args, **kwargs)
                (source / "private-draft").write_text("user's new draft\n")

            with patch.object(discovery_module.shutil, "copyfileobj", side_effect=dirtying_copy):
                with self.assertRaises(DirtySourceError):
                    create_snapshot(fresh, target)
            self.assertFalse(target.exists())
            self.assertEqual((source / "private-draft").read_text(), "user's new draft\n")
            self.assertEqual((source / "README.md").read_text(), "fixture\n")

    def test_tracked_symlinks_are_rejected_without_reading_the_target(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            make_repo(source)
            outside = Path(directory) / "secret"
            outside.write_text("private\n")
            (source / "link").symlink_to(outside)
            subprocess.run(["git", "-C", str(source), "add", "link"], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-qm", "symlink fixture"], check=True)
            with self.assertRaises(DiscoveryError):
                clean_snapshot(source, Path(directory) / "snapshot")
            self.assertEqual(outside.read_text(), "private\n")


class SandboxBoundaryTests(unittest.TestCase):
    def test_sandbox_command_contains_required_isolation_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("anti_slop_core.sandbox.sys.platform", "linux"), patch("anti_slop_core.sandbox.shutil.which", return_value="/usr/bin/bwrap"):
                command = Sandbox(directory).argv(["/bin/true"])
            self.assertIn("--unshare-net", command)
            self.assertIn("--unshare-user", command)
            self.assertIn("--die-with-parent", command)
            self.assertIn("/anti-slop-resources.py", command)
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
            with patch("anti_slop_core.sandbox.sys.platform", "linux"), patch("anti_slop_core.sandbox.shutil.which", return_value="/usr/bin/bwrap"):
                sandbox = Sandbox(workspace)
                command = sandbox.argv(["/bin/true"], str(subdir))
                self.assertEqual(command[command.index("--chdir") + 1], "/workspace/subdir")
                for cwd in ("../outside", "escape", str(outside)):
                    with self.subTest(cwd=cwd), self.assertRaises(ValueError):
                        sandbox.argv(["/bin/true"], cwd)

    def test_unspecified_timeout_still_has_a_finite_execution_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("anti_slop_core.sandbox.sys.platform", "linux"), patch("anti_slop_core.sandbox.shutil.which", return_value="/usr/bin/bwrap"), patch("anti_slop_core.sandbox.run_bounded", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as process:
                Sandbox(directory).run(["/bin/true"], timeout=None)
            self.assertGreater(process.call_args.kwargs["limits"].timeout_seconds, 0)
            self.assertLessEqual(process.call_args.kwargs["limits"].timeout_seconds, 300)

    def test_bubblewrap_startup_failure_is_unavailable_not_a_project_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.CompletedProcess([], 1, b"", b"bwrap: loopback: Failed to create NETLINK_ROUTE socket: Operation not permitted\n")
            with patch("anti_slop_core.sandbox.sys.platform", "linux"), patch("anti_slop_core.sandbox.shutil.which", return_value="/usr/bin/bwrap"), patch("anti_slop_core.sandbox.run_bounded", return_value=result):
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
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return sandbox


if __name__ == "__main__":
    unittest.main()
