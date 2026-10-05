"""Real process capture tests plus real Linux/Bubblewrap resource enforcement."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from anti_slop_core.artifacts import ArtifactStore
from anti_slop_core.checks import run_check
from anti_slop_core.models import AttemptStatus, CheckSpec, CheckStatus
from anti_slop_core.process_limits import OutputLimitExceeded, ProcessLimits, run_bounded
from anti_slop_core.sandbox import Sandbox, SandboxUnavailable


class TrustedLimitedProcess:
    """Trusted fixture only: this double makes no isolation assertion."""
    def __init__(self, workspace, limits):
        self.workspace, self.limits = Path(workspace), limits

    def run(self, command, cwd=".", timeout=None):
        return run_bounded(command, cwd=self.workspace / cwd, timeout=timeout, limits=self.limits)


class CaptureLimitTests(unittest.TestCase):
    def test_limits_are_immutable_and_reject_unbounded_values(self):
        limits = ProcessLimits()
        with self.assertRaises(FrozenInstanceError):
            limits.output_bytes = 0
        for kwargs in ({"output_bytes": 0}, {"processes": -1}, {"timeout_seconds": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ProcessLimits(**kwargs)

    def test_exact_aggregate_boundary_preserves_both_captures(self):
        result = run_bounded([sys.executable, "-c", "import os; os.write(1,b'a'*1000); os.write(2,b'b'*1000)"],
                             limits=ProcessLimits(output_bytes=2000), timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"a" * 1000)
        self.assertEqual(result.stderr, b"b" * 1000)

    def test_flood_terminates_and_never_certifies_a_successful_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore("output-flood", directory)
            store.create()
            fixture = TrustedLimitedProcess(directory, ProcessLimits(output_bytes=4096))
            spec = CheckSpec("flood", (sys.executable, "-c", "import os; os.write(1,b'a'*3000); os.write(2,b'b'*3000)"))
            record, refs = run_check(spec, fixture, store)
            self.assertEqual(record.status, CheckStatus.FAILED)
            self.assertEqual(record.attempts[0].status, AttemptStatus.FAILED)
            self.assertIsNone(record.attempts[0].exit_code)
            stdout, stderr = (store.read(ref) for ref in refs)
            self.assertLessEqual(len(stdout) + len(stderr), 4096)
            self.assertIn(b"aggregate stdout/stderr limit", stderr)
            self.assertTrue(stdout or stderr.startswith(b"b"))

    def test_unlimited_producer_is_killed_under_the_capture_cap(self):
        started = time.monotonic()
        with self.assertRaises(OutputLimitExceeded) as caught:
            run_bounded([sys.executable, "-c", "import os\nwhile True: os.write(1,b'x'*65536)"],
                        limits=ProcessLimits(output_bytes=2048), timeout=5)
        self.assertLess(time.monotonic() - started, 5)
        self.assertLessEqual(len(caught.exception.stdout) + len(caught.exception.stderr), 2048)

    def test_signal_termination_is_failed_with_bounded_explicit_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore("signal-limit", directory)
            store.create()
            fixture = TrustedLimitedProcess(directory, ProcessLimits(output_bytes=256))
            command = (sys.executable, "-c", "import os,signal; os.write(1,b'x'*256); os.kill(os.getpid(),signal.SIGTERM)")
            record, refs = run_check(CheckSpec("signal", command), fixture, store)
            self.assertEqual(record.status, CheckStatus.FAILED)
            self.assertLess(record.attempts[0].exit_code, 0)
            captured = b"".join(store.read(ref) for ref in refs)
            self.assertLessEqual(len(captured), 256)
            self.assertIn(b"check terminated by signal", captured)

    @unittest.skipUnless(hasattr(os, "fork"), "requires POSIX process groups")
    def test_timeout_kills_descendant_even_after_parent_exits_with_inherited_pipe(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "descendant-survived"
            code = ("import os,time,sys\n"
                    "if os.fork() == 0:\n time.sleep(0.7)\n open(sys.argv[1],'w').write('survived')\n os._exit(0)\n"
                    "os.write(1,b'parent-exited\\n'); os._exit(0)\n")
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                run_bounded([sys.executable, "-c", code, str(marker)], timeout=0.3)
            self.assertIn(b"parent-exited", caught.exception.stdout)
            self.assertIn(b"check timed out", caught.exception.stderr)
            time.sleep(0.8)
            self.assertFalse(marker.exists(), "timeout left an inherited-pipe descendant alive")

    def test_nonlinux_is_explicitly_unavailable_without_launching_a_check(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("anti_slop_core.sandbox.sys.platform", "darwin"), patch("anti_slop_core.sandbox.run_bounded") as launch:
                with self.assertRaisesRegex(SandboxUnavailable, "requires Linux"):
                    Sandbox(directory)
                launch.assert_not_called()


class RealSandboxResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        try:
            probe = Sandbox(self.workspace).run(["/bin/true"], timeout=5)
        except SandboxUnavailable as exc:
            self.skipTest(f"real Bubblewrap unavailable: {exc}")
        self.assertEqual(probe.returncode, 0, probe.stderr.decode(errors="replace"))

    def check(self, code, limits):
        store = ArtifactStore("resource-limit", str(self.root / "evidence"))
        store.create()
        record, refs = run_check(CheckSpec("limit", ("/usr/bin/python3", "-c", code)),
                                 Sandbox(self.workspace, limits), store)
        self.assertEqual(record.status, CheckStatus.FAILED)
        self.assertEqual(record.attempts[0].status, AttemptStatus.FAILED)
        return b"".join(store.read(ref) for ref in refs)

    def test_file_size_limit_stops_check_without_passing_or_growing_file(self):
        captured = self.check("with open('large','wb',buffering=0) as f: f.write(b'x'*65536); f.write(b'y')",
                              ProcessLimits(file_size_bytes=4096))
        self.assertLessEqual((self.workspace / "large").stat().st_size, 4096)
        self.assertIn(b"File too large", captured)

    def test_address_space_limit_is_a_nonpass_not_a_silent_success(self):
        captured = self.check("data=bytearray(128*1024*1024)", ProcessLimits(address_space_bytes=64*1024*1024))
        self.assertIn(b"MemoryError", captured)

    def test_resource_policy_is_applied_inside_actual_sandbox(self):
        result = Sandbox(self.workspace, ProcessLimits(open_files=64, processes=32)).run([
            "/usr/bin/python3", "-c",
            "import resource; assert resource.getrlimit(resource.RLIMIT_NOFILE)==(64,64); "
            "assert resource.getrlimit(resource.RLIMIT_NPROC)==(32,32); "
            "assert resource.getrlimit(resource.RLIMIT_CORE)==(0,0); print('bounded')",
        ], timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(result.stdout.strip(), b"bounded")

    def test_timeout_tears_down_bubblewrap_descendant_with_new_session(self):
        code = ("import os,time\n"
                "if os.fork() == 0:\n os.setsid()\n time.sleep(1)\n open('escaped','w').write('alive')\n os._exit(0)\n"
                "print('ready',flush=True)\ntime.sleep(20)\n")
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            Sandbox(self.workspace).run(["/usr/bin/python3", "-c", code], timeout=0.5)
        self.assertIn(b"ready", caught.exception.stdout)
        time.sleep(1.1)
        self.assertFalse((self.workspace / "escaped").exists())

    def test_output_flood_fails_in_real_sandbox_with_bounded_evidence(self):
        captured = self.check("import os\nwhile True: os.write(2,b'x'*65536)", ProcessLimits(output_bytes=4096))
        self.assertLessEqual(len(captured), 4096)
        self.assertIn(b"aggregate stdout/stderr limit", captured)


if __name__ == "__main__":
    unittest.main()
