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

    def test_artifact_requires_hash_and_size(self):
        from anti_slop_core.models import ArtifactRef
        with tempfile.TemporaryDirectory() as home:
            store = ArtifactStore("run-metadata", home)
            store.create()
            ref = store.put_bytes("capture", b"evidence")
            for incomplete in (ArtifactRef(ref.path), ArtifactRef(ref.path, ref.sha256), ArtifactRef(ref.path, size_bytes=ref.size_bytes)):
                with self.subTest(ref=incomplete):
                    self.assertFalse(store.verify(incomplete))

    def test_internal_symlink_cannot_stand_in_for_declared_artifact(self):
        from anti_slop_core.models import ArtifactRef
        with tempfile.TemporaryDirectory() as home:
            store = ArtifactStore("run-symlink", home)
            store.create()
            ref = store.put_bytes("original", b"evidence")
            (store.root / "alias").symlink_to("original")
            alias = ArtifactRef("alias", ref.sha256, ref.size_bytes)
            self.assertFalse(store.verify(alias))


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

    def test_unsandboxed_attempt_cannot_be_evidence_of_pass(self):
        from dataclasses import replace
        from anti_slop_core.models import ArtifactRef
        record = self._record(ArtifactRef("stdout", "a" * 64, 0), ArtifactRef("stderr", "b" * 64, 0))
        record = replace(record, attempts=(replace(record.attempts[0], sandboxed=False),))
        self.assertNotEqual(derive_check_status(record), CheckStatus.PASSED)

    def test_programmatic_omission_cannot_certify_a_pass(self):
        from anti_slop_core.models import ArtifactRef
        attempt = CommandAttempt(
            "unit", ("true",), ".", AttemptStatus.PASSED, 0,
            stdout_artifact=ArtifactRef("stdout", "a" * 64, 0),
            stderr_artifact=ArtifactRef("stderr", "b" * 64, 0),
        )
        self.assertFalse(attempt.sandboxed)
        self.assertEqual(derive_check_status(CheckRecord("unit", CheckStatus.PASSED, (attempt,))),
                         CheckStatus.FAILED)

    def test_declared_artifact_metadata_must_match_attempt_metadata(self):
        from dataclasses import replace
        from anti_slop_core.manifest import validate_manifest_artifacts
        from anti_slop_core.models import ManifestStatus, RunManifest, RunMode
        with tempfile.TemporaryDirectory() as home:
            store = ArtifactStore("run-mismatch", home)
            store.create()
            stdout = store.put_bytes("stdout", b"verified")
            stderr = store.put_bytes("stderr", b"")
            record = self._record(replace(stdout, media_type="application/json"), stderr)
            manifest = RunManifest("run-mismatch", RunMode.DIAGNOSE, "/repo", "/snapshot", ManifestStatus.PASSED, (record,), (), (stdout, stderr))
            with self.assertRaises(ValueError):
                validate_manifest_artifacts(manifest, store)

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

    def test_write_manifest_cannot_pass_without_write_gate_provenance(self):
        from anti_slop_core.manifest import validate_manifest_artifacts
        from anti_slop_core.models import ManifestStatus, RunManifest, RunMode
        with tempfile.TemporaryDirectory() as home:
            store = ArtifactStore("run-forged-write", home)
            store.create()
            stdout = store.put_bytes("stdout", b"passed\n")
            stderr = store.put_bytes("stderr", b"")
            record = self._record(stdout, stderr)
            manifest = RunManifest("run-forged-write", RunMode.REFACTOR, "/repo", "/snapshot", ManifestStatus.PASSED, (record,), (), (stdout, stderr))
            with self.assertRaises(ValueError):
                validate_manifest_artifacts(manifest, store)


if __name__ == "__main__":
    unittest.main()
