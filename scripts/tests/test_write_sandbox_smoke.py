"""Real CLI/Bubblewrap integration, explicitly skipped if isolation cannot start."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from anti_slop_core.artifacts import ArtifactStore
from anti_slop_core.manifest import validate_manifest_artifacts
from anti_slop_core.models import ManifestStatus
from anti_slop_core.sandbox import Sandbox, SandboxUnavailable
from anti_slop_core.schema import load_run_manifest
from tests.helpers import commit_fixture, tree_identity
from tests.test_write_acceptance import CONTRACT, ORIGINAL, REGRESSION, SIMPLIFIED, change, step


class RealWriteSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        probe_workspace = self.root / "probe"
        probe_workspace.mkdir()
        try:
            probe = Sandbox(probe_workspace).run(["/bin/true"], timeout=5)
        except SandboxUnavailable as exc:
            self.skipTest(f"real Bubblewrap unavailable: {exc}")
        self.assertEqual(probe.returncode, 0, probe.stderr.decode(errors="replace"))
        self.source = self.root / "source"
        commit_fixture(self.source, {"calc.py": ORIGINAL, "contract.py": CONTRACT})
        self.before = tree_identity(self.source)

    def run_cli(self, mode="refactor", steps=None, **overrides):
        payload = {
            "repo_path": str(self.source), "snapshot_root": str(self.root / "snapshot"), "mode": mode,
            "checks": [{"id": "contract", "argv": ["/usr/bin/python3", "-B", "contract.py"]}],
            "objective": "Remove the redundant zero case", "behavior_budget": "preserve",
            "allowed_paths": ["calc.py"], "oracle_checks": ["contract"], "oracle_paths": ["contract.py"],
            "limits": {"max_files": 1, "max_changed_lines": 30, "max_steps": 2},
            "steps": steps if steps is not None else [step()],
        }
        payload.update(overrides)
        spec = self.root / "spec.json"
        spec.write_text(json.dumps(payload))
        env = dict(os.environ, HERMES_HOME=str(self.root / "evidence"))
        runner = Path(__file__).resolve().parents[1] / "run.py"
        result = subprocess.run([sys.executable, str(runner), mode, "--spec", str(spec)], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertTrue(result.stdout, result.stderr)
        output = json.loads(result.stdout)
        manifest = load_run_manifest(Path(output["manifest"]).read_text())
        store = ArtifactStore(manifest.run_id, str(self.root / "evidence"))
        validate_manifest_artifacts(manifest, store)
        self.assertEqual(tree_identity(self.source), self.before)
        return result, manifest, store

    def test_real_cli_refactor_verifies_and_exports_replayable_patch(self):
        result, manifest, store = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), SIMPLIFIED)
        subprocess.run(["git", "-C", str(self.source), "apply", "--check", str(store.root / "write/final.patch")], check=True)

    def test_real_cli_repair_recovers_failed_step_and_retains_green_step(self):
        result, manifest, store = self.run_cli("repair-slop", [step(), step("regression", [change(before=SIMPLIFIED, after=REGRESSION)])])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), SIMPLIFIED)
        self.assertFalse((store.root / "write/final.patch").exists())
        audit = json.loads((store.root / "write/evidence.json").read_text())
        self.assertEqual([record["status"] for record in audit["steps"]], ["passed", "rolled_back"])

    def test_mounted_absolute_verifier_cannot_be_weakened_with_production(self):
        verifier = CONTRACT.replace("from calc import price\n", "from calc import price\nfrom oracle_values import EXPECTED_TOTAL\n")
        verifier = verifier.replace("price(3, 4) == 12", "price(3, 4) == EXPECTED_TOTAL")
        (self.source / "contract.py").write_text(verifier)
        (self.source / "oracle_values.py").write_text("EXPECTED_TOTAL = 12\n")
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.source), "commit", "-qm", "Independent oracle value"], check=True)
        self.before = tree_identity(self.source)
        result, manifest, store = self.run_cli(
            steps=[step("weaken-mounted-verifier", [change(after=REGRESSION),
                        change("contract.py", verifier, "print('passed')\n")])],
            checks=[{"id": "contract", "argv": ["/usr/bin/python3", "-B", "/workspace/contract.py"]}],
            allowed_paths=["calc.py", "contract.py"], oracle_paths=["oracle_values.py"],
            limits={"max_files": 2, "max_changed_lines": 30, "max_steps": 1})
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotEqual(manifest.status, ManifestStatus.PASSED)
        self.assertEqual((self.root / "snapshot/contract.py").read_text(), verifier)
        self.assertEqual((self.root / "snapshot/calc.py").read_text(), ORIGINAL)
        self.assertFalse((store.root / "write/final.patch").exists())


if __name__ == "__main__":
    unittest.main()
