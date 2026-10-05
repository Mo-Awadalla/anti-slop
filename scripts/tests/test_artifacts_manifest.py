import tempfile
import unittest
from pathlib import Path

from anti_slop_core.artifacts import ArtifactError, ArtifactStore
from anti_slop_core.manifest import derive_check_status
from anti_slop_core.models import (
    AttemptStatus,
    CheckRecord,
    CheckStatus,
    CommandAttempt,
)


class ArtifactIntegrityTests(unittest.TestCase):
    def test_artifact_round_trip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as home:
            store = ArtifactStore("run-artifacts", home)
            store.create()
            ref = store.put_bytes("checks/unit.stdout", b"ok\n", "text/plain")

            self.assertTrue(store.verify(ref))
            self.assertEqual(store.read(ref), b"ok\n")

            (store.root / ref.path).write_bytes(b"tampered\n")
            self.assertFalse(store.verify(ref))

    def test_artifact_paths_are_exclusive_and_traversal_safe(self):
        with tempfile.TemporaryDirectory() as home:
            store = ArtifactStore("run-artifacts", home)
            store.create()
            store.put_bytes("one.log", b"one")
            with self.assertRaises(ArtifactError):
                store.put_bytes("one.log", b"two")
            with self.assertRaises(ArtifactError):
                store.put_bytes("../escape.log", b"no")


class ManifestIntegrityTests(unittest.TestCase):
    def _record(self, stdout=None, stderr=None):
        attempt = CommandAttempt(
            "unit", ("/bin/true",), ".", AttemptStatus.PASSED, 0,
            1.0, stdout, stderr, True,
        )
        return CheckRecord("unit", CheckStatus.PENDING, (attempt,))

    def test_pass_requires_both_artifacts_in_verified_set(self):
        record = self._record()
        self.assertNotEqual(
            derive_check_status(record, artifact_paths=set()),
            CheckStatus.PASSED,
        )

    def test_stable_zero_attempt_with_verified_artifacts_passes(self):
        from anti_slop_core.models import ArtifactRef
        stdout = ArtifactRef("stdout", "a" * 64, 0, "text/plain")
        stderr = ArtifactRef("stderr", "b" * 64, 0, "text/plain")
        record = self._record(stdout, stderr)
        self.assertEqual(
            derive_check_status(record, artifact_paths={"stdout", "stderr"}),
            CheckStatus.PASSED,
        )

    def test_manifest_artifact_tampering_invalidates_pass(self):
        from anti_slop_core.manifest import validate_manifest_artifacts
        from anti_slop_core.models import ArtifactRef, ManifestStatus, RunManifest, RunMode
        with tempfile.TemporaryDirectory() as home:
            store = ArtifactStore("run-integrity", home)
            store.create()
            stdout = store.put_bytes("stdout", b"")
            stderr = store.put_bytes("stderr", b"")
            record = self._record(stdout, stderr)
            manifest = RunManifest("run-integrity", RunMode.DIAGNOSE, "/repo", "/snapshot", ManifestStatus.PASSED, (record,), (), (stdout, stderr))
            (store.root / "stdout").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                validate_manifest_artifacts(manifest, store)


if __name__ == "__main__":
    unittest.main()
