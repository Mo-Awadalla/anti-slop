"""Consumer-visible interchange and honest metadata boundary coverage."""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from anti_slop_core.artifacts import ArtifactStore
from anti_slop_core.cli import main
from anti_slop_core.hotspots import rank_hotspots
from anti_slop_core.manifest import derive_manifest_status, write_manifest
from anti_slop_core.models import AttemptStatus, CheckRecord, CheckStatus, CommandAttempt, RunManifest, RunMode
from anti_slop_core.sarif import export_sarif, import_sarif
from anti_slop_core.schema import SchemaError
from tests.helpers import commit_fixture


def sarif_document(path='hot.py', tool='fixture-analyzer'):
    return {'version': '2.1.0', 'runs': [{'tool': {'driver': {'name': tool, 'version': '1',
            'rules': [{'id': 'R1', 'name': 'Observed pattern', 'defaultConfiguration': {'level': 'note'}}]}},
            'results': [{'ruleIndex': 0, 'message': {'text': 'Inspect this context'},
                         'properties': {'antiSlopPriority': 7},
                         'locations': [{'physicalLocation': {'artifactLocation': {'uri': path},
                                        'region': {'startLine': 1, 'startColumn': 2}}}]}]}]}


class InterchangeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'repo'
        commit_fixture(self.repo, {'hot.py': 'a = 1\n', 'cold.py': 'b = 1\n'})

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(list(map(str, args)))
        return status, stdout.getvalue(), stderr.getvalue()

    def capture_manifest(self, document):
        store = ArtifactStore('captured-run', str(self.root / 'home'))
        store.create()
        # Execute a real, trusted fixture command. The capture is explicitly
        # unsandboxed and cannot certify a passing runner check.
        workspace = self.root / 'snapshot'
        workspace.mkdir()
        command = (sys.executable, '-c', 'print(__import__(\"sys\").argv[1],end=\"\")', json.dumps(document))
        process = subprocess.run(command, cwd=workspace, capture_output=True, check=True)
        stdout = store.put_bytes('checks/analyzer/stdout.json', process.stdout)
        stderr = store.put_bytes('checks/analyzer/stderr.txt', process.stderr)
        attempt = CommandAttempt('analyzer', command, str(workspace), AttemptStatus.PASSED,
                                 exit_code=0, stdout_artifact=stdout, stderr_artifact=stderr, sandboxed=False)
        record = CheckRecord('analyzer', CheckStatus.FAILED, (attempt,))
        status = derive_manifest_status((record,), artifact_paths={stdout.path, stderr.path})
        manifest = RunManifest('captured-run', RunMode.DIAGNOSE, str(self.repo), str(self.root / 'snapshot'),
                               status, (record,), artifacts=(stdout, stderr))
        path = store.root / 'manifest.json'
        write_manifest(path, manifest)
        return path, store, stdout

    def test_recorded_capture_cli_round_trip_keeps_observations_separate(self):
        path, store, ref = self.capture_manifest(sarif_document())
        signals = self.root / 'signals.json'
        status, _, error = self.cli('import-sarif', '--manifest', path, '--check', 'analyzer', '--output', signals)
        self.assertEqual(status, 0, error)
        document = json.loads(signals.read_text())
        self.assertEqual(document['capture']['artifact']['sha256'], ref.sha256)
        observation = document['signals'][0]
        self.assertEqual(observation['level'], 'note')
        self.assertEqual(observation['priority'], 7)
        self.assertEqual(observation['locations'], [{'path': 'hot.py', 'line': 1, 'column': 2}])
        for judgment in ('severity', 'confidence', 'impact', 'counterargument', 'recommended_action'):
            self.assertNotIn(judgment, observation)
        output = self.root / 'roundtrip.sarif'
        status, _, error = self.cli('export-sarif', '--signals', signals, '--output', output)
        self.assertEqual(status, 0, error)
        imported = import_sarif(output.read_bytes(), self.repo)
        self.assertEqual(imported['signals'][0]['level'], 'note')
        self.assertEqual(imported['signals'][0]['priority'], 7)
        self.assertEqual(imported['signals'][0]['message'], observation['message'])
        self.assertEqual(imported['signals'][0]['locations'], observation['locations'])
        self.assertTrue(store.verify(ref))

    def test_tampered_capture_rejected_before_output(self):
        path, store, ref = self.capture_manifest(sarif_document())
        (store.root / ref.path).write_bytes(b'{}')
        output = self.root / 'signals.json'
        status, _, error = self.cli('import-sarif', '--manifest', path, '--check', 'analyzer', '--output', output)
        self.assertEqual(status, 2)
        self.assertIn('artifact verification failed', error)
        self.assertFalse(output.exists())

    def test_recorded_capture_requires_existing_check_attempt(self):
        path, _, _ = self.capture_manifest(sarif_document())
        for check, attempt in [('missing', '1'), ('analyzer', '0'), ('analyzer', '2')]:
            status, _, _ = self.cli('import-sarif', '--manifest', path, '--check', check, '--attempt', attempt,
                                    '--output', self.root / ('bad-' + check + attempt))
            self.assertEqual(status, 2)

    def test_indexed_artifact_and_nested_uri_bases(self):
        document = sarif_document()
        run = document['runs'][0]
        run['originalUriBaseIds'] = {'ROOT': {'uri': self.repo.as_uri() + '/'}, 'SRC': {'uri': './', 'uriBaseId': 'ROOT'}}
        run['artifacts'] = [{'location': {'uri': 'hot.py', 'uriBaseId': 'SRC'}}]
        run['results'][0]['locations'][0]['physicalLocation']['artifactLocation'] = {'index': 0}
        self.assertEqual(import_sarif(json.dumps(document), self.repo)['signals'][0]['locations'][0]['path'], 'hot.py')

    def test_missing_locations_remain_unlocated_and_multiple_tools_export(self):
        document = sarif_document()
        document['runs'][0]['results'][0].pop('locations')
        second = sarif_document(tool='another-tool')['runs'][0]
        second['results'][0]['locations'] = [{'logicalLocations': [{'name': 'f'}]}]
        document['runs'].append(second)
        signals = import_sarif(json.dumps(document), self.repo)
        self.assertEqual([signal['locations'] for signal in signals['signals']], [[], []])
        self.assertEqual(signals['signals'][1]['omitted_logical_locations'], 1)
        exported = export_sarif(signals)
        self.assertEqual([run['tool']['driver']['name'] for run in exported['runs']], ['fixture-analyzer', 'another-tool'])
        self.assertEqual(len(export_sarif(signals, tool_name='another-tool')['runs']), 1)
        with self.assertRaises(SchemaError):
            export_sarif(signals, tool_name='absent')

    def test_extensions_and_message_templates(self):
        document = sarif_document()
        run = document['runs'][0]
        run['tool']['extensions'] = [{'name': 'extension', 'rules': [{'id': 'E', 'messageStrings': {'why': {'text': 'Observed {0}'}}}]}]
        result = run['results'][0]
        result.pop('ruleIndex')
        result['rule'] = {'index': 0, 'toolComponent': {'index': 0}}
        result['message'] = {'id': 'why', 'arguments': ['call']}
        signal = import_sarif(json.dumps(document), self.repo)['signals'][0]
        self.assertEqual(signal['tool']['name'], 'extension')
        self.assertEqual(signal['rule']['id'], 'E')
        self.assertEqual(signal['message'], 'Observed call')

    def test_malformed_essential_input_and_traversal(self):
        for uri in ('../secret', '%2e%2e/secret', '/etc/passwd', 'https://example.com/file', 'hot.py?query=1', 'bad%ZZ', 'a\\b'):
            with self.subTest(uri=uri), self.assertRaises((SchemaError, ValueError)):
                import_sarif(json.dumps(sarif_document(path=uri)), self.repo)
        for mutation in ('version', 'message', 'level', 'index', 'region', 'base'):
            document = sarif_document()
            result = document['runs'][0]['results'][0]
            if mutation == 'version':
                document['version'] = '2.0.0'
            elif mutation == 'message':
                result['message'] = {}
            elif mutation == 'level':
                result['level'] = []
            elif mutation == 'index':
                result['ruleIndex'] = 5
            elif mutation == 'region':
                result['locations'][0]['physicalLocation']['region']['startLine'] = True
            else:
                result['locations'][0]['physicalLocation']['artifactLocation']['uriBaseId'] = 'UNKNOWN'
            with self.subTest(mutation=mutation), self.assertRaises(SchemaError):
                import_sarif(json.dumps(document), self.repo)
        with self.assertRaises(SchemaError):
            import_sarif('{"version":"2.1.0","version":"2.1.0","runs":[]}', self.repo)
        with self.assertRaises(SchemaError):
            import_sarif('{"version":"2.1.0","runs":[],"x":NaN}', self.repo)
        (self.repo / 'escape').symlink_to(self.root)
        with self.assertRaises(SchemaError):
            import_sarif(json.dumps(sarif_document(path='escape/secret')), self.repo)

    def test_cyclic_bases_and_bad_artifact_indices_rejected_by_cli(self):
        for mode in ('cycle', 'index'):
            document = sarif_document()
            run = document['runs'][0]
            artifact = run['results'][0]['locations'][0]['physicalLocation']['artifactLocation']
            if mode == 'cycle':
                run['originalUriBaseIds'] = {'A': {'uri': './', 'uriBaseId': 'B'}, 'B': {'uri': './', 'uriBaseId': 'A'}}
                artifact['uriBaseId'] = 'A'
            else:
                artifact.clear()
                artifact['index'] = 1
            source = self.root / (mode + '.sarif')
            source.write_text(json.dumps(document))
            target = self.root / (mode + '.json')
            status, _, error = self.cli('import-sarif', '--sarif', source, '--repo', self.repo, '--output', target)
            self.assertEqual(status, 2, error)
            self.assertFalse(target.exists())

    def test_encoded_filename_and_text_priority_round_trip(self):
        document = sarif_document(path='odd%23name.py')
        document['runs'][0]['results'][0]['properties']['antiSlopPriority'] = 'triage-first'
        signals = import_sarif(json.dumps(document), self.repo)
        self.assertEqual(signals['signals'][0]['locations'][0]['path'], 'odd#name.py')
        again = import_sarif(json.dumps(export_sarif(signals)), self.repo)
        self.assertEqual(again['signals'][0]['priority'], 'triage-first')
        self.assertEqual(again['signals'][0]['locations'], signals['signals'][0]['locations'])

    def add_hot_commit(self):
        (self.repo / 'hot.py').write_text('a = 2\n')
        subprocess.run(['git', '-C', str(self.repo), 'add', 'hot.py'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'commit', '-qm', 'change hot'], check=True)

    def test_cli_churn_ranking_preserves_levels_and_priority(self):
        self.add_hot_commit()
        document = sarif_document(path='cold.py')
        second = sarif_document(path='hot.py')['runs'][0]['results'][0]
        second['level'] = 'warning'
        document['runs'][0]['results'].append(second)
        signals = self.root / 'signals.json'
        signals.write_text(json.dumps(import_sarif(json.dumps(document), self.repo)))
        output = self.root / 'ranked.json'
        status, _, error = self.cli('rank-hotspots', '--input', signals, '--repo', self.repo, '--lookback-days', '90', '--output', output)
        self.assertEqual(status, 0, error)
        ranked = json.loads(output.read_text())
        self.assertEqual([item['locations'][0]['path'] for item in ranked['signals']], ['hot.py', 'cold.py'])
        self.assertEqual([item['churn']['commits'] for item in ranked['signals']], [2, 1])
        self.assertEqual([item['level'] for item in ranked['signals']], ['warning', 'note'])
        self.assertEqual([item['priority'] for item in ranked['signals']], [7, 7])
        self.assertEqual(ranked['history']['lookback_days'], 90)
        self.assertEqual(len(ranked['history']['revision']), 40)

    def test_churn_includes_merged_branch_changes_reverted_before_merge(self):
        def git(*args):
            return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        original_branch = git("branch", "--show-current")
        git("checkout", "-qb", "reverted-change")
        self.add_hot_commit()
        (self.repo / "hot.py").write_text("a = 1\n")
        git("add", "hot.py")
        git("commit", "-qm", "restore hot")
        git("checkout", "-q", original_branch)
        (self.repo / "cold.py").write_text("b = 2\n")
        git("add", "cold.py")
        git("commit", "-qm", "change cold")
        git("merge", "-q", "--no-ff", "reverted-change", "-m", "merge reverted changes")
        signals = import_sarif(json.dumps(sarif_document()), self.repo)
        ranked = rank_hotspots(signals, self.repo, lookback_days=90)
        self.assertEqual(ranked["signals"][0]["churn"]["commits"], 3)
        self.assertEqual(ranked["signals"][0]["level"], signals["signals"][0]["level"])
        self.assertEqual(ranked["signals"][0]["priority"], signals["signals"][0]["priority"])

    def test_churn_findings_preserve_semantic_judgments(self):
        self.add_hot_commit()
        findings = [{'id': path, 'title': 'Review', 'source': 'check', 'evidence_refs': ['checks/out'],
                     'severity': severity, 'impact': 'Local context', 'confidence': 0.5,
                     'recommended_action': 'Inspect', 'counterargument': 'May be intentional', 'path': path}
                    for path, severity in [('cold.py', 'high'), ('hot.py', 'low')]]
        source = self.root / 'findings.json'
        source.write_text(json.dumps(findings))
        target = self.root / 'ranked-findings.json'
        status, _, error = self.cli('rank-hotspots', '--input', source, '--repo', self.repo, '--lookback-days', '90', '--output', target)
        self.assertEqual(status, 0, error)
        ranked = json.loads(target.read_text())['findings']
        self.assertEqual([item['severity'] for item in ranked], ['low', 'high'])
        self.assertEqual([{key: value for key, value in item.items() if key != 'churn'} for item in ranked], list(reversed(findings)))

    def test_shallow_and_unavailable_history_are_explicit(self):
        self.add_hot_commit()
        shallow = self.root / 'shallow'
        subprocess.run(['git', 'clone', '-q', '--depth', '1', self.repo.as_uri(), str(shallow)], check=True)
        signals = import_sarif(json.dumps(sarif_document()), self.repo)
        ranked = rank_hotspots(signals, shallow, lookback_days=90)
        self.assertEqual(ranked['signals'][0]['churn']['commits'], 1)
        self.assertTrue(any(value.startswith('shallow-history:') for value in ranked['history']['limitations']))
        unavailable = rank_hotspots(signals, self.root, lookback_days=90)
        self.assertIsNone(unavailable['signals'][0]['churn']['commits'])
        self.assertIsNone(unavailable['history']['revision'])
        self.assertTrue(any(value.startswith('history-unavailable:') for value in unavailable['history']['limitations']))

    def test_real_completed_diagnose_cli_emits_unsigned_exact_hashes(self):
        spec = {'repo_path': str(self.repo), 'snapshot_root': str(self.root / 'snapshot'), 'mode': 'diagnose',
                'checks': [{'id': 'capture', 'argv': ['python3', '-c', 'print("actual fixture output")']}]}
        spec_path = self.root / 'spec.json'
        spec_path.write_bytes((json.dumps(spec) + '\r\n').encode('utf-8'))
        with patch.dict(os.environ, {'HERMES_HOME': str(self.root / 'home')}):
            status, stdout, error = self.cli('diagnose', '--spec', spec_path)
        self.assertIn(status, (0, 1), error)
        result = json.loads(stdout)
        manifest_path = Path(result['manifest'])
        original = manifest_path.read_bytes()
        provenance = json.loads(Path(result['provenance']).read_text())
        self.assertEqual(provenance['_type'], 'https://in-toto.io/Statement/v1')
        self.assertEqual(provenance['predicateType'], 'https://slsa.dev/provenance/v1')
        self.assertEqual(provenance['subject'], [{'name': 'manifest.json', 'digest': {'sha256': hashlib.sha256(original).hexdigest()}}])
        definition = provenance['predicate']['buildDefinition']
        self.assertEqual(definition['externalParameters']['specInputSha256'], hashlib.sha256(spec_path.read_bytes()).hexdigest())
        self.assertEqual(definition['externalParameters']['spec']['checks'][0]['argv'], spec['checks'][0]['argv'])
        manifest = json.loads(original)
        self.assertEqual(definition['resolvedDependencies'][0]['digest']['gitCommit'], manifest['discovery']['head'])
        self.assertEqual(definition['internalParameters']['checks'], manifest['checks'])
        byproducts = provenance['predicate']['runDetails']['byproducts']
        self.assertEqual({item['name']: item['digest']['sha256'] for item in byproducts},
                         {item['path']: item['sha256'] for item in manifest['artifacts']})
        self.assertNotIn('signature', provenance)
        self.assertNotIn('provenance.json', [item['name'] for item in byproducts])
        self.assertEqual(manifest_path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
