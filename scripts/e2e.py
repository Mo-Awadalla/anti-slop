"""Exercise actual CLI trust boundaries; requires operational Linux Bubblewrap."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

RUNNER = Path(__file__).resolve().with_name('run.py')
ORIGINAL = 'def multiply(a, b):\n    if a == 0:\n        return 0\n    return a * b\n'
SIMPLIFIED = 'def multiply(a, b):\n    return a * b\n'
BROKEN = 'def multiply(a, b):\n    return a * b + 1\n'
CONTRACT = 'from calc import multiply\nfrom oracle_helpers import expect\nexpect(multiply(2, 3), 6)\nexpect(multiply(0, 9), 0)\nexpect(multiply(-2, 4), -8)\n'
HELPER = 'def expect(actual, expected):\n    assert actual == expected, (actual, expected)\n'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def fixture(root, name, files):
    repo = root / name / 'source'
    repo.mkdir(parents=True)
    git(repo, 'init', '-q')
    git(repo, 'config', 'user.email', 'e2e@example.test')
    git(repo, 'config', 'user.name', 'E2E')
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'fixture')
    return repo


def identity(repo):
    return {p.relative_to(repo).as_posix(): digest(p.read_bytes()) for p in repo.rglob('*')
            if p.is_file() and '.git' not in p.relative_to(repo).parts}


def cli(root, *args, expected=0):
    result = subprocess.run([sys.executable, str(RUNNER), *map(str, args)], capture_output=True,
                            text=True, timeout=60, env=dict(os.environ, HERMES_HOME=str(root / 'evidence')))
    assert result.returncode == expected, (args, result.returncode, result.stdout, result.stderr)
    return json.loads(result.stdout) if result.stdout.strip() else {'stderr': result.stderr}


def run(root, repo, label, command='diagnose', checks=None, steps=None, allowed=None, protected=None, oracles=None, expected=0, extra_args=()):
    spec = {'repo_path': str(repo), 'snapshot_root': str(repo.parent / label), 'mode': command,
            'checks': checks or [{'id': 'contract', 'argv': ['/usr/bin/python3', '-B', 'contract.py']}]}
    if command != 'diagnose':
        spec.update(objective='Remove the redundant zero branch', behavior_budget='preserve',
                    allowed_paths=allowed or ['calc.py'], protected_paths=protected or [],
                    oracle_checks=['contract'], oracle_paths=oracles or ['contract.py'],
                    limits={'max_files': 2, 'max_changed_lines': 50, 'max_steps': 2}, steps=steps or [])
    spec_path = repo.parent / (label + '.json')
    save(spec_path, spec)
    before = identity(repo)
    result = cli(root, command, '--spec', spec_path, *extra_args, expected=expected)
    assert identity(repo) == before, 'CLI changed source checkout'
    manifest = json.loads(Path(result['manifest']).read_text())
    provenance = json.loads(Path(result['provenance']).read_text())
    assert provenance['_type'] == 'https://in-toto.io/Statement/v1'
    assert provenance['predicateType'] == 'https://slsa.dev/provenance/v1'
    for subject in provenance['subject']:
        artifact = Path(result['manifest']).parent / subject['name']
        assert digest(artifact.read_bytes()) == subject['digest']['sha256'], subject
    return result, manifest, Path(spec['snapshot_root'])


def change(before, after, path='calc.py'):
    return {'path': path, 'before_sha256': digest(before.encode()), 'content': after}


def step(name, before=ORIGINAL, after=SIMPLIFIED, path='calc.py'):
    return {'id': name, 'description': name, 'changes': [change(before, after, path)]}


def exercise(root):
    outcomes = []
    repo = fixture(root, 'preserve', {'calc.py': ORIGINAL, 'contract.py': CONTRACT,
                                     'oracle_helpers.py': HELPER, '.gitignore': '.env\n'})
    (repo / '.env').write_text('SECRET=e2e-private-value\n')
    result, manifest, snap = run(root, repo, 'valid', 'refactor', steps=[step('simplify')],
                                protected=['future_helper.py'])
    assert manifest['status'] == 'passed'
    assert not (snap / '.env').exists(), 'ignored secret reached check workspace'
    assert (snap / 'calc.py').read_text() == SIMPLIFIED
    patch = Path(result['manifest']).parent / 'write/final.patch'
    git(repo, 'apply', '--check', str(patch))
    outcomes.append({'case': 'preservation_and_secret_exclusion', 'verdict': 'verified'})
    assert not (snap / 'future_helper.py').exists()
    outcomes.append({'case': 'absent_protected_path_preserves_valid_write', 'verdict': 'verified'})

    result, manifest, snap = run(root, repo, 'rollback', 'repair-slop',
                                steps=[step('simplify'), step('regression', SIMPLIFIED, BROKEN)], expected=1)
    assert manifest['status'] != 'passed'
    assert (snap / 'calc.py').read_text() == SIMPLIFIED
    assert not (Path(result['manifest']).parent / 'write/final.patch').exists()
    outcomes.append({'case': 'failed_step_restores_previous_green_tree', 'verdict': 'verified'})

    result, manifest, snap = run(root, repo, 'helper', 'refactor', allowed=['oracle_helpers.py'],
                                steps=[step('weaken-helper', HELPER, 'def expect(actual, expected):\n    return True\n', 'oracle_helpers.py')], expected=1)
    assert manifest['status'] != 'passed'
    assert (snap / 'oracle_helpers.py').read_text() == HELPER
    outcomes.append({'case': 'imported_assertion_helper_is_immutable', 'verdict': 'verified'})

    mounted_step = {'id': 'weaken-mounted-verifier', 'description': 'Reject a verifier bypass',
                    'changes': [change(ORIGINAL, BROKEN), change(CONTRACT, 'print("passed")\n', 'contract.py')]}
    result, manifest, snap = run(root, repo, 'mounted-verifier', 'refactor',
                                checks=[{'id': 'contract', 'argv': ['/usr/bin/python3', '-B', '/workspace/contract.py']}],
                                allowed=['calc.py', 'contract.py'], oracles=['oracle_helpers.py'],
                                steps=[mounted_step], expected=1)
    assert manifest['status'] != 'passed'
    assert (snap / 'contract.py').read_text() == CONTRACT
    assert (snap / 'calc.py').read_text() == ORIGINAL
    outcomes.append({'case': 'mounted_absolute_verifier_is_immutable', 'verdict': 'verified'})

    mutation = fixture(root, 'mutation', {'calc.py': BROKEN, 'contract.py': CONTRACT, 'oracle_helpers.py': HELPER})
    result, manifest, snap = run(root, mutation, 'red', 'repair-slop', steps=[step('fix', BROKEN, SIMPLIFIED)], expected=1)
    assert (snap / 'calc.py').read_text() == BROKEN
    assert manifest['status'] != 'passed'
    outcomes.append({'case': 'oracle_kills_mutant_and_red_baseline_stops_edits', 'verdict': 'verified'})

    mutation_spec = json.loads((root / 'preserve/valid.json').read_text())
    mutation_spec['steps'] = [step('wrong-product', ORIGINAL, BROKEN), step('equivalent-simplification'),
                              step('timeout', ORIGINAL, 'def multiply(a, b):\n    while True:\n        pass\n'),
                              step('signal-resource', ORIGINAL,
                                   'def multiply(a, b):\n    import os, signal\n    os.kill(os.getpid(), signal.SIGKILL)\n'),
                              step('file-resource', ORIGINAL,
                                   'def multiply(a, b):\n    import resource\n'
                                   '    resource.setrlimit(resource.RLIMIT_FSIZE, (4096, 4096))\n'
                                   '    with open("/tmp/resource-output", "wb", buffering=0) as output:\n'
                                   '        output.write(b"x" * 8192)\n        output.write(b"x")\n'
                                   '    return a * b\n')]
    mutation_spec['steps'].append(step('descriptor-resource', ORIGINAL,
                                      'def multiply(a, b):\n    import os, resource\n'
                                      '    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))\n'
                                      '    descriptors = []\n    while True:\n'
                                      '        descriptors.append(os.open("/dev/null", os.O_RDONLY))\n'))
    mutation_spec['limits']['max_steps'] = 6
    mutation_spec['checks'][0]['timeout_seconds'] = 0.5
    mutation_spec_path = root / 'mutation-spec.json'
    mutation_report = root / 'mutation-audit.json'
    save(mutation_spec_path, mutation_spec)
    cli(root, 'mutation-audit', '--spec', mutation_spec_path, '--output', mutation_report)
    sensitivity = json.loads(mutation_report.read_text())
    assert sensitivity['counts'] == {'detected': 1, 'survived': 1, 'inconclusive': 4}, sensitivity
    for name in ('signal-resource', 'file-resource', 'descriptor-resource'):
        assert next(item for item in sensitivity['mutations'] if item['id'] == name)['outcome'] == 'inconclusive'
    outcomes.append({'case': 'on_demand_mutation_detection_and_survivor_reporting', 'verdict': 'verified'})

    result, manifest, snap = run(root, repo, 'tamper', 'refactor', steps=[step('simplify')])
    manifest_path = Path(result['manifest'])
    patch = manifest_path.parent / 'write/final.patch'
    original_patch = patch.read_bytes()
    changed = original_patch.replace(b'     return a * b\n', b'-    return a * b\n+    return a * b + 1\n')
    assert changed != original_patch, 'tamper control did not alter patch bytes'
    patch.write_bytes(changed)
    for artifact in manifest['artifacts']:
        if artifact['path'] == 'write/final.patch':
            artifact['sha256'], artifact['size_bytes'] = digest(changed), len(changed)
    save(manifest_path, manifest)
    findings = repo.parent / 'empty-findings.json'
    save(findings, [])
    rejected = cli(root, 'validate-findings', '--manifest', manifest_path, '--findings', findings, expected=2)
    assert 'patch' in rejected['stderr'].lower() or 'replay' in rejected['stderr'].lower(), rejected
    outcomes.append({'case': 'rehashed_patch_body_tamper_rejected', 'verdict': 'verified'})

    flood = fixture(root, 'flood', {'flood.py': 'import os\nwhile True:\n    os.write(1, b"x" * 65536)\n'})
    result, manifest, snap = run(root, flood, 'limited', checks=[{'id': 'flood', 'argv': ['/usr/bin/python3', 'flood.py'], 'timeout_seconds': 10}], expected=1)
    assert manifest['status'] != 'passed'
    capture_refs = [a for a in manifest['artifacts'] if a['path'].endswith(('.stdout', '.stderr'))]
    assert sum(a['size_bytes'] for a in capture_refs) <= 1024 * 1024
    errors = b''.join((Path(result['manifest']).parent / a['path']).read_bytes()
                      for a in manifest['artifacts'] if a['path'].endswith('.stderr'))
    assert b'limit' in errors.lower(), errors
    outcomes.append({'case': 'output_flood_is_bounded_failure', 'verdict': 'verified'})

    sarif = {'version': '2.1.0', 'runs': [{'tool': {'driver': {'name': 'FixtureScanner'}}, 'results': [
        {'ruleId': 'duplication', 'level': 'warning', 'message': {'text': 'Review repeated policy'},
         'locations': [{'physicalLocation': {'artifactLocation': {'uri': path}, 'region': {'startLine': 1}}}]}
        for path in ['cold.py', 'hot.py']]}]}
    repo = fixture(root, 'signals', {'cold.py': 'value = 1\n', 'hot.py': 'value = 1\n',
                                   'tool.sarif': json.dumps(sarif),
                                   'capture.py': 'import json\nfrom pathlib import Path\n'
                                                 'document = json.loads(Path("tool.sarif").read_text())\n'
                                                 'run = document["runs"][0]\n'
                                                 'run["originalUriBaseIds"] = {"ROOT": {"uri": Path.cwd().as_uri() + "/"}}\n'
                                                 'first = run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]\n'
                                                 'first["uri"] = Path(first["uri"]).resolve().as_uri()\n'
                                                 'run["results"][1]["locations"][0]["physicalLocation"]["artifactLocation"]["uriBaseId"] = "ROOT"\n'
                                                 'print(json.dumps(document))\n'})
    for value in [2, 3]:
        (repo / 'hot.py').write_text(f'value = {value}\n')
        git(repo, 'add', 'hot.py'); git(repo, 'commit', '-qm', f'hot change {value}')
    result, manifest, snap = run(root, repo, 'scan', checks=[{'id': 'scanner', 'argv': ['/usr/bin/python3', 'capture.py']}])
    signals, ranked, exported = [repo.parent / name for name in ['signals.json', 'ranked.json', 'results.sarif']]
    cli(root, 'import-sarif', '--manifest', result['manifest'], '--check', 'scanner', '--output', signals)
    cli(root, 'rank-hotspots', '--input', signals, '--repo', repo, '--lookback-days', '90', '--revision', 'HEAD', '--output', ranked)
    ranked_data = json.loads(ranked.read_text())
    assert ranked_data['signals'][0]['locations'][0]['path'] == 'hot.py', ranked_data
    assert all(signal['level'] == 'warning' for signal in ranked_data['signals'])
    cli(root, 'export-sarif', '--signals', ranked, '--output', exported)
    exported_data = json.loads(exported.read_text())
    assert exported_data['version'] == '2.1.0'
    assert len(exported_data['runs'][0]['results']) == 2
    outcomes.append({'case': 'captured_sarif_history_ranking_export_and_provenance', 'verdict': 'verified'})

    result, manifest, snap = run(root, repo, 'ci-scan',
                                checks=[{'id': 'scanner', 'argv': ['/usr/bin/python3', 'capture.py']}],
                                extra_args=('--sarif-check', 'scanner', '--sarif-tool', 'FixtureScanner'))
    emitted = json.loads(Path(result['sarif']).read_text())
    assert len(emitted['runs']) == 1
    assert {location['physicalLocation']['artifactLocation']['uri']
            for item in emitted['runs'][0]['results'] for location in item['locations']} == {'cold.py', 'hot.py'}
    outcomes.append({'case': 'diagnosis_emits_captured_sarif_for_read_only_ci', 'verdict': 'verified'})

    limits = {}
    for name in ['memory.max', 'pids.max', 'cpu.max']:
        path = Path('/sys/fs/cgroup') / name
        if path.exists():
            limits[name] = path.read_text().strip()
    return {'kind': 'actual-cli-efficacy', 'cases': outcomes, 'cgroup_limits': limits,
            'limits': 'Synthetic contract scenarios, not general maintenance or model efficacy evidence.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new writable evidence directory')
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    result = exercise(root)
    save(root / 'results.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
