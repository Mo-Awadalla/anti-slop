"""Launcher boundary behavior; kernel isolation is exercised by Linux E2E."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import container
from anti_slop_core.schema import SchemaError


class ContainerLauncherTests(unittest.TestCase):
    def test_help_succeeds_without_docker(self):
        launcher = Path(container.__file__)
        result = subprocess.run([sys.executable, str(launcher), "--help"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout)

    def test_missing_docker_reports_dependency_without_host_fallback(self):
        diagnostic = io.StringIO()
        with patch("container.shutil.which", return_value=None), patch("container.subprocess.run") as launch:
            with contextlib.redirect_stderr(diagnostic):
                code = container.main(["test"])
        self.assertEqual(code, 2)
        launch.assert_not_called()

    def test_writable_source_overlap_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            spec = root / "spec.json"
            spec.write_text(json.dumps({"repo_path": str(source), "snapshot_root": str(root / "snap"),
                                        "mode": "diagnose", "checks": [{"id": "unit", "argv": ["/bin/true"]}]}))
            args = container.parser().parse_args(["run", "--spec", str(spec), "--snapshot", str(source / "nested"),
                                                  "--evidence", str(root / "evidence")])
            with self.assertRaises(ValueError):
                container.docker_command(args)
            self.assertFalse((source / "nested").exists())
            self.assertFalse((root / "evidence").exists())

    def test_invalid_raw_specs_are_rejected_without_rewrite_or_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            valid = {"repo_path": str(source), "snapshot_root": str(root / "snap"),
                     "mode": "diagnose", "checks": [{"id": "unit", "argv": ["/bin/true"]}]}
            duplicate = json.dumps(valid)[:-1] + ', "repo_path": ' + json.dumps(str(source)) + "}"
            invalid_path = dict(valid, snapshot_root="relative")
            missing_checks = dict(valid)
            del missing_checks["checks"]
            for raw in (duplicate, json.dumps(invalid_path), json.dumps(missing_checks)):
                with self.subTest(raw=raw):
                    spec = root / "spec.json"
                    spec.write_text(raw)
                    snapshot, evidence = root / "snapshot", root / "evidence"
                    args = container.parser().parse_args(["run", "--spec", str(spec), "--snapshot", str(snapshot),
                                                          "--evidence", str(evidence)])
                    with self.assertRaises(SchemaError):
                        container.docker_command(args)
                    self.assertEqual(spec.read_text(), raw)
                    self.assertFalse(snapshot.exists())
                    self.assertFalse(evidence.exists())


@unittest.skipUnless(sys.platform == "linux" and os.getuid() == 0, "requires Linux root to exercise real UID mapping")
class RootOutputDirectoryTests(unittest.TestCase):
    def _run_arguments(self, root):
        source = root / "source"
        source.mkdir(mode=0o755)
        spec = root / "spec.json"
        spec.write_text(json.dumps({"repo_path": str(source), "snapshot_root": str(root / "original-snapshot"),
                                   "mode": "diagnose", "checks": [{"id": "unit", "argv": ["/bin/true"]}]}))
        return container.parser().parse_args(["run", "--spec", str(spec), "--snapshot", str(root / "snapshot"),
                                               "--evidence", str(root / "evidence")])

    def _mapped_identity(self, command):
        uid, gid = map(int, command[command.index("--user") + 1].split(":"))
        self.assertNotEqual(uid, 0)
        return uid, gid

    def _write_as_mapped_user(self, command, root):
        uid, gid = self._mapped_identity(command)
        result = subprocess.run(
            [sys.executable, "-c",
             "import json,pathlib,sys; root=pathlib.Path(sys.argv[1]); "
             "json.loads(next((root/'evidence').glob('container-spec-*.json')).read_text()); "
             "(root/'snapshot'/'workspace').mkdir(); "
             "(root/'snapshot'/'workspace'/'result').write_text('snapshot'); "
             "(root/'evidence'/'result').write_text('evidence')", str(root)],
            user=uid, group=gid, extra_groups=(), capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((root / "snapshot/workspace/result").read_text(), "snapshot")
        self.assertEqual((root / "evidence/result").read_text(), "evidence")

    def test_new_mounts_and_spec_are_usable_by_the_real_nonroot_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o755)
            args = self._run_arguments(root)
            source_before = (root / "source").stat()
            root_before = root.stat()
            command = container.docker_command(args)
            self._write_as_mapped_user(command, root)
            for path, before in ((root, root_before), (root / "source", source_before)):
                after = path.stat()
                self.assertEqual((after.st_uid, after.st_gid, after.st_mode),
                                 (before.st_uid, before.st_gid, before.st_mode))

    def test_exec_evidence_mount_is_writable_without_reowning_existing_directories(self):
        for existing in (False, True):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                root.chmod(0o755)
                evidence = root / "evidence"
                before = None
                if existing:
                    evidence.mkdir()
                    evidence.chmod(0o777)
                    before = evidence.stat()
                args = container.parser().parse_args(["exec", "--evidence", str(evidence), "--", "/bin/true"])
                command = container.docker_command(args)
                uid, gid = self._mapped_identity(command)
                result = subprocess.run(
                    [sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('result')",
                     str(evidence / "result")],
                    user=uid, group=gid, extra_groups=(), capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((evidence / "result").read_text(), "result")
                if before is not None:
                    after = evidence.stat()
                    self.assertEqual((after.st_uid, after.st_gid, after.st_mode),
                                     (before.st_uid, before.st_gid, before.st_mode))


    def test_existing_user_directories_and_contents_keep_ownership_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o755)
            args = self._run_arguments(root)
            for name in ("snapshot", "evidence"):
                path = root / name
                path.mkdir(mode=0o750)
                os.chown(path, 65534, 65534)
            existing = root / "evidence/user-file"
            existing.write_text("untouched")
            existing.chmod(0o640)
            before = {path: path.stat() for path in (root / "snapshot", root / "evidence", existing)}
            command = container.docker_command(args)
            self._write_as_mapped_user(command, root)
            for path, metadata in before.items():
                after = path.stat()
                self.assertEqual((after.st_uid, after.st_gid, after.st_mode),
                                 (metadata.st_uid, metadata.st_gid, metadata.st_mode))
            self.assertEqual(existing.read_text(), "untouched")

    def test_inaccessible_existing_mount_is_rejected_without_mutating_user_data(self):
        for name in ("snapshot", "evidence"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                args = self._run_arguments(root)
                blocked = root / name
                blocked.mkdir(mode=0o755)
                before = blocked.stat()
                with self.assertRaises(ValueError):
                    container.docker_command(args)
                after = blocked.stat()
                self.assertEqual((after.st_uid, after.st_gid, after.st_mode),
                                 (before.st_uid, before.st_gid, before.st_mode))
                other = root / ("evidence" if name == "snapshot" else "snapshot")
                self.assertFalse(other.exists())
                self.assertFalse(any(blocked.iterdir()))

    @unittest.skipUnless(shutil.which("git"), "requires real Git")
    def test_trust_is_limited_to_the_mapped_root_owned_source(self):
        from tests.test_discovery_sandbox import make_repo

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o755)
            args = self._run_arguments(root)
            source = root / "source"
            untrusted = root / "untrusted"
            untrusted.mkdir(mode=0o755)
            make_repo(source)
            make_repo(untrusted)
            command = container.docker_command(args)
            uid, gid = self._mapped_identity(command)
            environment = os.environ.copy()
            for index, argument in enumerate(command):
                if argument == "--env":
                    key, value = command[index + 1].split("=", 1)
                    # Resolve the Docker bind target to its host fixture path.
                    environment[key] = str(source) if value == "/source" else value
            environment["PYTHONPATH"] = str(Path(container.__file__).parent)
            probe = (
                "import pathlib,sys; from anti_slop_core.discovery import discover; "
                "info=discover(pathlib.Path(sys.argv[1])); "
                "assert not info.dirty and info.head"
            )
            trusted_result = subprocess.run([sys.executable, "-c", probe, str(source)], env=environment,
                                            user=uid, group=gid, extra_groups=(), capture_output=True, text=True)
            self.assertEqual(trusted_result.returncode, 0, trusted_result.stderr)
            untrusted_result = subprocess.run([sys.executable, "-c", probe, str(untrusted)], env=environment,
                                              user=uid, group=gid, extra_groups=(), capture_output=True, text=True)
            self.assertNotEqual(untrusted_result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
