"""Recorded sandbox URI mapping must not widen external SARIF trust."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from anti_slop_core.artifacts import ArtifactStore
from anti_slop_core.cli import main
from anti_slop_core.manifest import derive_manifest_status, write_manifest
from anti_slop_core.models import AttemptStatus, CheckRecord, CheckStatus, CommandAttempt, RunManifest, RunMode
from anti_slop_core.sarif import export_sarif, import_sarif
from anti_slop_core.schema import SchemaError


def sarif_document(location, *, artifacts=None, bases=None):
    run = {
        'tool': {'driver': {'name': 'recorded-analyzer'}},
        'results': [{'ruleId': 'R1', 'message': {'text': 'Review this calculation'},
                     'locations': [{'physicalLocation': {'artifactLocation': location,
                                                        'region': {'startLine': 1}}}]}],
    }
    if artifacts is not None:
        run['artifacts'] = artifacts
    if bases is not None:
        run['originalUriBaseIds'] = bases
    return {'version': '2.1.0', 'runs': [run]}


class RecordedSarifPathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Exercise URI quoting of the receiving repository root as well.
        self.repo = self.root / 'source #1'
        self.repo.mkdir()
        (self.repo / 'calc.py').write_text('answer = 42\n')
        self.next_capture = 0

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(list(map(str, args)))
        return status, stderr.getvalue()

    def capture_manifest(self, document, *, sandboxed=True):
        # Build immutable evidence fixtures, not a substitute runner. Tests here
        # concern the importer boundary and make no claim about real isolation.
        run_id = f'capture-{self.next_capture}'
        self.next_capture += 1
        store = ArtifactStore(run_id, str(self.root / ('home-' + run_id)))
        store.create()
        stdout = store.put_bytes('checks/analyzer/stdout.json', json.dumps(document).encode())
        stderr = store.put_bytes('checks/analyzer/stderr.txt', b'')
        attempt = CommandAttempt('analyzer', ('python3', 'analyzer.py'), '.', AttemptStatus.PASSED,
                                 exit_code=0, stdout_artifact=stdout, stderr_artifact=stderr, sandboxed=sandboxed)
        record = CheckRecord('analyzer', CheckStatus.PASSED if sandboxed else CheckStatus.FAILED, (attempt,))
        status = derive_manifest_status((record,), artifact_paths={stdout.path, stderr.path})
        manifest = RunManifest(run_id, RunMode.DIAGNOSE, str(self.repo), str(self.root / 'snapshot'),
                               status, (record,), artifacts=(stdout, stderr))
        path = store.root / 'manifest.json'
        write_manifest(path, manifest)
        return path, store, stdout

    def recorded_import(self, document):
        manifest, _, _ = self.capture_manifest(document)
        output = manifest.parent / 'signals.json'
        status, error = self.cli('import-sarif', '--manifest', manifest, '--check', 'analyzer', '--output', output)
        self.assertEqual(status, 0, error)
        return json.loads(output.read_text())

    def test_recorded_absolute_locations_round_trip_as_repository_relative(self):
        for uri in ('file:///workspace/calc.py', '/workspace/calc.py',
                    'file://localhost/workspace/calc.py', 'file:///work%73pace/%63alc.py'):
            with self.subTest(uri=uri):
                signals = self.recorded_import(sarif_document({'uri': uri}))
                self.assertEqual(signals['signals'][0]['locations'], [{'path': 'calc.py', 'line': 1}])
                exported = export_sarif(signals)
                physical = exported['runs'][0]['results'][0]['locations'][0]['physicalLocation']
                self.assertEqual(physical['artifactLocation']['uri'], 'calc.py')
                again = import_sarif(json.dumps(exported), self.repo)
                self.assertEqual(again['signals'][0]['locations'], signals['signals'][0]['locations'])

    def test_artifact_indices_and_recursive_original_bases_use_the_same_mapping(self):
        documents = [
            sarif_document({'index': 0}, artifacts=[{'location': {'uri': 'file:///workspace/calc.py'}}]),
            sarif_document({'uri': 'calc.py', 'uriBaseId': 'ROOT'},
                           bases={'ROOT': {'uri': 'file:///workspace/'}}),
            sarif_document({'index': 0},
                           artifacts=[{'location': {'uri': 'calc.py', 'uriBaseId': 'SRC'}}],
                           bases={'ROOT': {'uri': 'file:///work%73pace/'},
                                  'SRC': {'uri': './', 'uriBaseId': 'ROOT'}}),
        ]
        for document in documents:
            with self.subTest(document=document):
                signals = self.recorded_import(document)
                self.assertEqual(signals['signals'][0]['locations'], [{'path': 'calc.py', 'line': 1}])

    def test_encoded_filename_survives_recorded_import_and_external_export_import(self):
        signals = self.recorded_import(sarif_document({'uri': 'file:///workspace/odd%23name%20%25.py'}))
        self.assertEqual(signals['signals'][0]['locations'][0]['path'], 'odd#name %.py')
        exported = export_sarif(signals)
        uri = exported['runs'][0]['results'][0]['locations'][0]['physicalLocation']['artifactLocation']['uri']
        self.assertEqual(uri, 'odd%23name%20%25.py')
        again = import_sarif(json.dumps(exported), self.repo)
        self.assertEqual(again['signals'][0]['locations'], signals['signals'][0]['locations'])

    def test_recorded_escapes_are_rejected_through_all_location_routes(self):
        unsafe = (
            'file:///workspace/../secret.py', 'file:///workspace/%2e%2e/secret.py',
            'file:///workspace/%2e%2e%2fsecret.py', 'file:///workspace-escape/calc.py',
            'file://remote/workspace/calc.py', '//remote/workspace/calc.py',
            'file:///workspace/calc.py?query=1', 'file:///workspace/calc.py#fragment',
            'file:///workspace/bad%ZZ', 'file:///workspace/a%5cb',
            'file:///workspace/a%00b', 'https://example.invalid/workspace/calc.py',
        )
        for uri in unsafe:
            for route in ('direct', 'index', 'base'):
                if route == 'direct':
                    document = sarif_document({'uri': uri})
                elif route == 'index':
                    document = sarif_document({'index': 0}, artifacts=[{'location': {'uri': uri}}])
                else:
                    document = sarif_document({'uri': 'calc.py', 'uriBaseId': 'ROOT'}, bases={'ROOT': {'uri': uri}})
                with self.subTest(uri=uri, route=route), self.assertRaises((SchemaError, ValueError)):
                    import_sarif(json.dumps(document), self.repo, recorded_workspace=True)
        document = sarif_document({'uri': '%2e%2e/secret.py', 'uriBaseId': 'ROOT'},
                                 bases={'ROOT': {'uri': 'file:///workspace/'}})
        with self.assertRaises(SchemaError):
            import_sarif(json.dumps(document), self.repo, recorded_workspace=True)
        (self.repo / 'escape').symlink_to(self.root)
        with self.assertRaises(SchemaError):
            import_sarif(json.dumps(sarif_document({'uri': 'file:///workspace/escape/secret.py'})),
                         self.repo, recorded_workspace=True)

    def test_external_import_cannot_inherit_the_recorded_root_allowance(self):
        documents = [
            sarif_document({'uri': 'file:///workspace/calc.py'}),
            sarif_document({'index': 0}, artifacts=[{'location': {'uri': '/workspace/calc.py'}}]),
            sarif_document({'uri': 'calc.py', 'uriBaseId': 'ROOT'}, bases={'ROOT': {'uri': 'file:///workspace/'}}),
        ]
        for index, document in enumerate(documents):
            # Metadata, including a scanner-supplied recorded label, grants no
            # authority. Only the validated manifest branch enables mapping.
            document['capture'] = {'kind': 'recorded-check'}
            source = self.root / f'external-{index}.sarif'
            source.write_text(json.dumps(document))
            output = self.root / f'external-{index}.json'
            with self.subTest(index=index):
                status, _ = self.cli('import-sarif', '--sarif', source, '--repo', self.repo, '--output', output)
                self.assertEqual(status, 2)
                self.assertFalse(output.exists())
                with self.assertRaises(SchemaError):
                    import_sarif(json.dumps(document), self.repo, capture={'kind': 'recorded-check'})
        # A preceding recorded import must not leak allowance to later imports.
        self.recorded_import(documents[0])
        with self.assertRaises(SchemaError):
            import_sarif(json.dumps(documents[0]), self.repo)

    def test_tampered_and_unsandboxed_records_cannot_enable_mount_mapping(self):
        document = sarif_document({'uri': 'file:///workspace/calc.py'})
        for mode in ('tampered', 'unsandboxed'):
            with self.subTest(mode=mode):
                manifest, store, ref = self.capture_manifest(document, sandboxed=mode != 'unsandboxed')
                if mode == 'tampered':
                    (store.root / ref.path).write_bytes(b'{}')
                output = manifest.parent / 'signals.json'
                status, _ = self.cli('import-sarif', '--manifest', manifest, '--check', 'analyzer', '--output', output)
                self.assertEqual(status, 2)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
