"""Observable staged-write outcomes on disposable repositories.

The fixture verifier has expectations authored separately from calc.py and
detects a real behavior mutation. These tests substitute trusted local command
execution for Bubblewrap; real isolation is covered by the smoke tests.
"""

import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anti_slop_core.artifacts import ArtifactStore
from anti_slop_core.manifest import validate_manifest_artifacts
from anti_slop_core.models import CheckStatus, ManifestStatus
from anti_slop_core.schema import SchemaError, load_run_manifest, load_run_spec
from tests.helpers import LocalFixtureSandbox, commit_fixture, digest, tree_identity


ORIGINAL = """def price(quantity, unit):
    total = quantity * unit
    if quantity == 0:
        return 0
    return total
"""
SIMPLIFIED = """def price(quantity, unit):
    return quantity * unit
"""
REGRESSION = """def price(quantity, unit):
    return quantity * unit + 1
"""
CONTRACT = """from calc import price

assert price(3, 4) == 12
assert price(0, 9) == 0
assert price(2, 0) == 0
assert price(-2, 5) == -10
assert price(4, 1.5) == 6
"""


def change(path="calc.py", before=ORIGINAL, after=SIMPLIFIED):
    return {"path": path, "before_sha256": digest(before) if before is not None else None, "content": after}


def step(identifier="remove-duplicate-zero", changes=None):
    return {"id": identifier, "description": "Remove the redundant zero branch while preserving multiplication results", "changes": changes or [change()]}


class WriteAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        commit_fixture(self.source, {"calc.py": ORIGINAL, "contract.py": CONTRACT, "README.md": "Run python3 -B contract.py\n"})
        self.original_tree = tree_identity(self.source)
        runner = patch("anti_slop_core.write_modes.BubblewrapSandbox", LocalFixtureSandbox)
        runner.start()
        self.addCleanup(runner.stop)

    def payload(self, **overrides):
        payload = {
            "repo_path": str(self.source),
            "snapshot_root": str(self.root / "snapshot"),
            "mode": "refactor",
            "checks": [{"id": "contract", "argv": ["/usr/bin/python3", "-B", "contract.py"]}],
            "objective": "Remove the duplicate zero case from price",
            "behavior_budget": "preserve",
            "allowed_paths": ["calc.py"],
            "oracle_checks": ["contract"],
            "oracle_paths": ["contract.py"],
            "limits": {"max_files": 1, "max_changed_lines": 20, "max_steps": 3},
            "steps": [step()],
        }
        payload.update(overrides)
        return payload

    def run_fixture(self, **overrides):
        from anti_slop_core.write_modes import run_write
        return run_write(load_run_spec(self.payload(**overrides)), hermes_home=str(self.root / "evidence"))

    def assert_source_untouched(self):
        self.assertEqual(tree_identity(self.source), self.original_tree)

    def test_small_atomic_refactor_exports_verified_patch_and_evidence(self):
        manifest, manifest_path, report_path = self.run_fixture()
        self.assertEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), SIMPLIFIED)
        self.assert_source_untouched()
        loaded = load_run_manifest(manifest_path.read_text())
        self.assertEqual(loaded.status, ManifestStatus.PASSED)
        store = ArtifactStore(manifest.run_id, str(self.root / "evidence"))
        validate_manifest_artifacts(loaded, store)
        patch_text = (store.root / "write/final.patch").read_text()
        self.assertIn("calc.py", patch_text)
        self.assertNotIn("contract.py", patch_text)
        import subprocess
        subprocess.run(["git", "-C", str(self.source), "apply", "--check", str(store.root / "write/final.patch")], check=True)
        evidence = json.loads((store.root / "write/evidence.json").read_text())
        self.assertIsInstance(evidence, dict)
        self.assertIn("Remove the duplicate zero case", report_path.read_text())

    def test_cli_executes_write_mode_and_exports_loadable_manifest(self):
        from anti_slop_core.cli import main
        spec_path = self.root / "spec.json"
        spec_path.write_text(json.dumps(self.payload()))
        output = io.StringIO()
        with patch.dict("os.environ", {"HERMES_HOME": str(self.root / "cli-evidence")}), patch("sys.stdout", output):
            code = main(["refactor", "--spec", str(spec_path)])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "passed")
        loaded = load_run_manifest(Path(result["manifest"]).read_text())
        self.assertEqual(loaded.status, ManifestStatus.PASSED)
        self.assert_source_untouched()

    def test_cli_rejects_mode_mismatch_before_any_snapshot_write(self):
        from anti_slop_core.cli import main
        spec_path = self.root / "spec.json"
        spec_path.write_text(json.dumps(self.payload(mode="diagnose")))
        with patch("sys.stderr", io.StringIO()):
            code = main(["repair-slop", "--spec", str(spec_path)])
        self.assertNotEqual(code, 0)
        self.assertFalse((self.root / "snapshot").exists())
        self.assert_source_untouched()

    def test_successful_write_manifest_cannot_drop_gate_artifacts(self):
        _, manifest_path, _ = self.run_fixture()
        original = json.loads(manifest_path.read_text())
        for missing in ("write/evidence.json", "write/final.patch"):
            with self.subTest(missing=missing):
                payload = dict(original)
                payload["artifacts"] = [ref for ref in original["artifacts"] if ref["path"] != missing]
                with self.assertRaises(SchemaError):
                    load_run_manifest(payload)

    def test_valid_hash_cannot_rescue_inconsistent_write_gate_evidence(self):
        from dataclasses import replace
        import copy
        import hashlib
        manifest, _, _ = self.run_fixture()
        store = ArtifactStore(manifest.run_id, str(self.root / "evidence"))
        original_ref = next(ref for ref in manifest.artifacts if ref.path == "write/evidence.json")
        original_data = (store.root / original_ref.path).read_bytes()
        audit = json.loads(original_data)
        mutations = []
        for field in ("completed", "source_unchanged"):
            changed = copy.deepcopy(audit)
            changed[field] = False
            mutations.append((field, changed))
        changed = copy.deepcopy(audit)
        changed["baseline"]["check_ids"] = ["invented-pass"]
        mutations.append(("unknown baseline check", changed))
        changed = copy.deepcopy(audit)
        changed["steps"][0]["status"] = "rolled_back"
        mutations.append(("failed step labelled complete", changed))
        changed = copy.deepcopy(audit)
        changed["final_patch_artifact"] = "other.patch"
        mutations.append(("foreign patch", changed))
        try:
            for label, changed in mutations:
                with self.subTest(mutation=label):
                    data = (json.dumps(changed) + "\n").encode()
                    (store.root / original_ref.path).write_bytes(data)
                    new_ref = replace(original_ref, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
                    forged = replace(manifest, artifacts=tuple(new_ref if ref.path == original_ref.path else ref for ref in manifest.artifacts))
                    with self.assertRaises(ValueError):
                        validate_manifest_artifacts(forged, store)
        finally:
            (store.root / original_ref.path).write_bytes(original_data)

    def test_repair_mode_uses_the_same_baseline_and_oracle_gates(self):
        manifest, _, _ = self.run_fixture(mode="repair-slop")
        self.assertEqual(manifest.status, ManifestStatus.PASSED)
        self.assert_source_untouched()

    def test_red_baseline_stops_before_supplied_patch(self):
        (self.source / "calc.py").write_text(REGRESSION)
        # This is a committed pre-existing defect, not dirty user work.
        import subprocess
        subprocess.run(["git", "-C", str(self.source), "commit", "-am", "baseline defect", "-q"], check=True)
        self.original_tree = tree_identity(self.source)
        manifest, _, _ = self.run_fixture(steps=[step(changes=[change(before=REGRESSION)])])
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), REGRESSION)
        self.assertTrue(any(record.status is CheckStatus.FAILED for record in manifest.checks))
        self.assert_source_untouched()

    def test_failed_second_step_restores_previous_verified_change(self):
        steps = [step(), step("inject-regression", [change(before=SIMPLIFIED, after=REGRESSION)]), step("never-execute", [change(before=REGRESSION, after="raise RuntimeError('should not reach')\n")])]
        manifest, manifest_path, _ = self.run_fixture(steps=steps)
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), SIMPLIFIED)
        self.assertTrue(any(record.status is CheckStatus.FAILED for record in manifest.checks))
        self.assertEqual(load_run_manifest(manifest_path.read_text()).status, manifest.status)
        self.assert_source_untouched()

    def test_no_steps_leaves_clean_control_unchanged(self):
        manifest, _, report_path = self.run_fixture(steps=[])
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), ORIGINAL)
        self.assert_source_untouched()
        self.assertIn("no", report_path.read_text().lower())

    def test_empty_required_checks_cannot_pass(self):
        try:
            manifest, _, _ = self.run_fixture(checks=[], oracle_checks=[])
        except SchemaError:
            pass
        else:
            self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assert_source_untouched()

    def test_missing_sandbox_never_executes_or_exports_verified_patch(self):
        from anti_slop_core.sandbox import SandboxUnavailable
        with patch("anti_slop_core.write_modes.BubblewrapSandbox", side_effect=SandboxUnavailable("fixture unsupported host")):
            manifest, manifest_path, _ = self.run_fixture()
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertFalse((manifest_path.parent / "write/final.patch").exists())
        self.assert_source_untouched()

    def test_stale_preimage_hash_does_not_modify_snapshot(self):
        manifest, _, _ = self.run_fixture(steps=[step(changes=[change(before="unexpected\n")])])
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), ORIGINAL)
        self.assert_source_untouched()

    def test_line_budget_blocks_before_export(self):
        manifest, manifest_path, _ = self.run_fixture(limits={"max_files": 1, "max_changed_lines": 1, "max_steps": 3})
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertFalse((manifest_path.parent / "write/final.patch").exists())
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), ORIGINAL)
        self.assert_source_untouched()

    def test_cumulative_file_budget_blocks_second_independent_file(self):
        steps = [step(), step("unrelated-readme", [change("README.md", "Run python3 -B contract.py\n", "Document multiplication\n")])]
        manifest, _, _ = self.run_fixture(allowed_paths=["calc.py", "README.md"], steps=steps)
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), SIMPLIFIED)
        self.assertEqual((self.root / "snapshot/README.md").read_text(), "Run python3 -B contract.py\n")
        self.assert_source_untouched()

    def test_immutable_oracle_cannot_be_weakened_to_make_regression_pass(self):
        try:
            manifest, _, _ = self.run_fixture(allowed_paths=["calc.py", "contract.py"], steps=[step(changes=[change(after=REGRESSION), change("contract.py", CONTRACT, "print('passed')\n")])])
        except SchemaError:
            pass
        else:
            self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
            self.assertEqual((self.root / "snapshot/contract.py").read_text(), CONTRACT)
        self.assert_source_untouched()

    def test_check_that_mutates_snapshot_cannot_certify_patch(self):
        import subprocess
        (self.source / "mutator.py").write_text("from pathlib import Path\nPath('calc.py').write_text('corrupt')\n")
        subprocess.run(["git", "-C", str(self.source), "add", "mutator.py"], check=True)
        subprocess.run(["git", "-C", str(self.source), "commit", "-qm", "mutating verifier fixture"], check=True)
        self.original_tree = tree_identity(self.source)
        checks = [{"id": "contract", "argv": ["/usr/bin/python3", "-B", "mutator.py"]}]
        manifest, _, _ = self.run_fixture(checks=checks)
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), ORIGINAL)
        self.assert_source_untouched()

    def test_check_that_creates_empty_directory_is_recovered(self):
        import subprocess
        (self.source / "mutator.py").write_text("from pathlib import Path\nPath('unreviewed').mkdir(exist_ok=True)\n")
        subprocess.run(["git", "-C", str(self.source), "add", "mutator.py"], check=True)
        subprocess.run(["git", "-C", str(self.source), "commit", "-qm", "directory-mutating verifier fixture"], check=True)
        self.original_tree = tree_identity(self.source)
        checks = [{"id": "contract", "argv": ["/usr/bin/python3", "-B", "mutator.py"]}]
        manifest, _, _ = self.run_fixture(checks=checks)
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertFalse((self.root / "snapshot/unreviewed").exists())
        self.assert_source_untouched()

    def test_check_argv_script_is_protected_even_when_oracle_names_a_helper(self):
        import subprocess
        (self.source / "helper.py").write_text("EXPECTED_TOTAL = 12\n")
        subprocess.run(["git", "-C", str(self.source), "add", "helper.py"], check=True)
        subprocess.run(["git", "-C", str(self.source), "commit", "-qm", "oracle helper fixture"], check=True)
        self.original_tree = tree_identity(self.source)
        manifest, _, _ = self.run_fixture(allowed_paths=["contract.py"], oracle_paths=["helper.py"],
                                          steps=[step("weaken-verifier", [change("contract.py", CONTRACT, "print('passed')\n")])])
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual((self.root / "snapshot/contract.py").read_text(), CONTRACT)
        self.assert_source_untouched()

    def test_non_deterministic_check_is_not_relabelled_green(self):
        calls = []

        class AlternatingSandbox(LocalFixtureSandbox):
            def run(self, command, cwd=".", timeout=None):
                import subprocess
                calls.append(1)
                return subprocess.CompletedProcess(command, len(calls) % 2, b"fixture output\n", b"")

        with patch("anti_slop_core.write_modes.BubblewrapSandbox", AlternatingSandbox):
            manifest, _, _ = self.run_fixture()
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertTrue(any(record.status is CheckStatus.FLAKY for record in manifest.checks))
        self.assert_source_untouched()

    def test_dirty_tree_is_stopped_without_consuming_user_edits(self):
        (self.source / "README.md").write_text("user draft\n")
        self.original_tree = tree_identity(self.source)
        manifest, _, _ = self.run_fixture()
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertFalse((self.root / "snapshot").exists())
        self.assert_source_untouched()

    def test_artifact_destination_cannot_modify_source_or_certified_snapshot(self):
        from anti_slop_core.write_modes import run_write
        spec = load_run_spec(self.payload())
        for home in (self.source / "evidence", self.root / "snapshot/evidence"):
            with self.subTest(home=home), self.assertRaises(ValueError):
                run_write(spec, hermes_home=str(home))
            self.assertFalse(home.exists())
            self.assert_source_untouched()

    def test_symlinked_source_cannot_be_followed_to_an_external_file(self):
        import subprocess
        outside = self.root / "outside.py"
        outside.write_text("external private source\n")
        (self.source / "calc.py").unlink()
        (self.source / "calc.py").symlink_to(outside)
        subprocess.run(["git", "-C", str(self.source), "commit", "-am", "symlink fixture", "-q"], check=True)
        self.original_tree = tree_identity(self.source)
        manifest, _, _ = self.run_fixture()
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual(outside.read_text(), "external private source\n")
        self.assert_source_untouched()

    def test_addition_and_deletion_export_reproducible_patch(self):
        # Git treats only LF as a patch line boundary. Keep Unicode separators,
        # CRLF, lone CR, and a missing final newline exactly in the output.
        added = "# Multiplication contract remains the verifier\r\na\u2028b\rend"
        changes = [change("note.txt", None, added), change("README.md", "Run python3 -B contract.py\n", None)]
        manifest, manifest_path, _ = self.run_fixture(allowed_paths=["note.txt", "README.md"], limits={"max_files": 2, "max_changed_lines": 20, "max_steps": 1}, steps=[step("replace-note", changes)])
        self.assertEqual(manifest.status, ManifestStatus.PASSED)
        self.assertFalse((self.root / "snapshot/README.md").exists())
        self.assertEqual((self.root / "snapshot/note.txt").read_bytes(), added.encode())
        import subprocess
        subprocess.run(["git", "-C", str(self.source), "apply", "--check", str(manifest_path.parent / "write/final.patch")], check=True)
        replay = self.root / "replay"
        subprocess.run(["git", "clone", "-q", str(self.source), str(replay)], check=True)
        subprocess.run(["git", "-C", str(replay), "apply", str(manifest_path.parent / "write/final.patch")], check=True)
        self.assertEqual((replay / "note.txt").read_bytes(), added.encode())
        self.assertFalse((replay / "README.md").exists())
        self.assert_source_untouched()


class WriteSchemaAcceptanceTests(unittest.TestCase):
    def payload(self):
        return {
            "repo_path": "/fixtures/source", "snapshot_root": "/fixtures/snapshot", "mode": "refactor",
            "checks": [{"id": "contract", "argv": ["/bin/true"]}], "objective": "Simplify multiplication",
            "behavior_budget": "preserve", "allowed_paths": ["calc.py"], "oracle_checks": ["contract"],
            "oracle_paths": ["contract.py"], "limits": {"max_files": 1, "max_changed_lines": 20, "max_steps": 1}, "steps": [step()],
        }

    def test_write_contract_accepts_both_executable_modes(self):
        for mode in ("refactor", "repair-slop"):
            payload = self.payload()
            payload["mode"] = mode
            self.assertEqual(load_run_spec(payload).mode.value, mode)

    def test_paths_cannot_escape_scope_or_touch_git_metadata(self):
        for path in ("../outside.py", "/etc/passwd", "calc.py/../other.py", ".git/config", "a\\b.py", "injected\n+++ b/other.py", "a\tpath", "null\x00path"):
            with self.subTest(path=path):
                payload = self.payload()
                payload["allowed_paths"] = [path]
                payload["steps"][0]["changes"][0]["path"] = path
                with self.assertRaises(SchemaError):
                    load_run_spec(payload)

    def test_step_cannot_use_file_outside_declared_scope(self):
        payload = self.payload()
        payload["steps"][0]["changes"][0]["path"] = "unrelated.py"
        with self.assertRaises(SchemaError):
            load_run_spec(payload)

    def test_step_limit_and_duplicate_step_ids_are_rejected(self):
        for steps in ([step(), step("two")], [step(), step()]):
            payload = self.payload()
            payload["steps"] = steps
            if steps[0]["id"] == steps[1]["id"]:
                payload["limits"]["max_steps"] = 2
            with self.assertRaises(SchemaError):
                load_run_spec(payload)

    def test_oracle_must_name_a_required_declared_check(self):
        for oracle in ("missing", "contract"):
            payload = self.payload()
            payload["oracle_checks"] = [oracle]
            payload["checks"][0]["required"] = False
            with self.assertRaises(SchemaError):
                load_run_spec(payload)

    def test_intentional_behavior_change_is_outside_preserve_contract(self):
        payload = self.payload()
        payload["behavior_budget"] = "intentional-change"
        with self.assertRaises(SchemaError):
            load_run_spec(payload)

    def test_missing_preimage_or_content_is_not_an_ambiguous_patch(self):
        for bad_change in ({"path": "calc.py", "before_sha256": None, "content": None}, {"path": "calc.py", "before_sha256": "fake", "content": SIMPLIFIED}):
            payload = self.payload()
            payload["steps"][0]["changes"] = [bad_change]
            with self.assertRaises(SchemaError):
                load_run_spec(payload)


if __name__ == "__main__":
    unittest.main()
