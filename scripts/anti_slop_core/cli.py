"""Public command-line interface for diagnosis, bounded writes and findings."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .diagnose import run_diagnose
from .findings import validate_findings
from .manifest import validate_manifest_artifacts
from .models import ManifestStatus, RunMode
from .schema import SchemaError, load_findings, load_run_manifest, load_run_spec
from .artifacts import ArtifactStore
from .write_modes import run_write

from .hotspots import rank_hotspots
from .manifest import artifact_to_dict
from .provenance import write_provenance
from .sarif import decode_json, export_sarif, import_sarif, load_signals

P0_SUBCOMMANDS = ('diagnose', 'validate-findings')
RUN_SUBCOMMANDS = ('diagnose', 'refactor', 'repair-slop')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='anti-slop')
    subparsers = parser.add_subparsers(dest='command', required=True)
    for name in RUN_SUBCOMMANDS:
        command = subparsers.add_parser(name, help='run explicit checks' if name == 'diagnose' else 'validate supplied bounded edits in an isolated snapshot')
        command.add_argument('--spec', required=True, type=Path)
        if name == 'diagnose':
            command.add_argument('--sarif-check', help='export this recorded stdout capture as SARIF')
            command.add_argument('--sarif-tool', help='export one tool name for its upload/category')
    findings = subparsers.add_parser('validate-findings', help='validate findings against a manifest')
    findings.add_argument('--manifest', required=True, type=Path)
    findings.add_argument('--findings', required=True, type=Path)
    sarif_import = subparsers.add_parser('import-sarif', help='normalize external tool observations, not certified findings')
    source = sarif_import.add_mutually_exclusive_group(required=True)
    source.add_argument('--sarif', type=Path)
    source.add_argument('--manifest', type=Path)
    sarif_import.add_argument('--repo', type=Path)
    sarif_import.add_argument('--check')
    sarif_import.add_argument('--attempt', type=int, default=1, help='one-based recorded attempt index')
    sarif_import.add_argument('--stream', choices=('stdout', 'stderr'), default='stdout')
    sarif_import.add_argument('--output', required=True, type=Path)
    sarif_export = subparsers.add_parser('export-sarif', help='export tool-signals without semantic judgments')
    sarif_export.add_argument('--signals', required=True, type=Path)
    sarif_export.add_argument('--tool', help='export one tool name for a separate upload/category')
    sarif_export.add_argument('--output', required=True, type=Path)
    hotspots = subparsers.add_parser('rank-hotspots', help='rank by optional Git touch counts without changing severity')
    hotspots.add_argument('--input', required=True, type=Path)
    hotspots.add_argument('--repo', required=True, type=Path)
    hotspots.add_argument('--lookback-days', required=True, type=int)
    hotspots.add_argument('--revision', default='HEAD')
    hotspots.add_argument('--output', required=True, type=Path)
    mutation = subparsers.add_parser('mutation-audit', help='audit supplied bounded mutants against recorded baseline checks')
    mutation.add_argument('--spec', required=True, type=Path)
    mutation.add_argument('--output', required=True, type=Path)
    return parser


def _read_json(path: Path):
    try:
        # Keep JSON text intact so the contract loaders can reject duplicate
        # keys and nonstandard constants before converting it to a mapping.
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        raise SchemaError(f'cannot read JSON {path}: {exc}') from exc

def _validated_manifest(path: Path):
    path = path.resolve()
    manifest = load_run_manifest(_read_json(path))
    store = ArtifactStore(manifest.run_id)
    store.root = path.parent
    validate_manifest_artifacts(manifest, store)
    return manifest, store


def _write_json(path: Path, document: dict):
    # Captures and manifests are immutable evidence, not output destinations.
    with path.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(document, indent=2, sort_keys=True) + '\n')


def _import_capture(args):
    if args.sarif is not None:
        if args.repo is None or args.check is not None:
            raise SchemaError('external SARIF requires --repo and does not accept --check')
        text = args.sarif.read_bytes()
        capture = {'kind': 'external', 'path': str(args.sarif.resolve()),
                   'sha256': hashlib.sha256(text).hexdigest()}
        return import_sarif(text, args.repo, capture=capture)
    if not args.check:
        raise SchemaError('recorded SARIF requires --check')
    manifest, store = _validated_manifest(args.manifest)
    if args.repo is not None and args.repo.resolve() != Path(manifest.repo_path).resolve():
        raise SchemaError('--repo disagrees with recorded repository')
    records = [record for record in manifest.checks if record.check_id == args.check]
    if len(records) != 1 or args.attempt < 1 or args.attempt > len(records[0].attempts):
        raise SchemaError('recorded check or attempt does not exist')
    attempt = records[0].attempts[args.attempt - 1]
    ref = attempt.stdout_artifact if args.stream == 'stdout' else attempt.stderr_artifact
    if ref is None:
        raise SchemaError('recorded attempt has no selected capture')
    text = store.read(ref)
    capture = {'kind': 'recorded-check', 'run_id': manifest.run_id, 'check_id': args.check,
               'attempt': args.attempt, 'stream': args.stream, 'artifact': artifact_to_dict(ref),
               'manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest()}
    return import_sarif(text, manifest.repo_path, capture=capture, recorded_workspace=attempt.sandboxed)



def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in RUN_SUBCOMMANDS:
            if args.command == 'diagnose' and bool(args.sarif_check) != bool(args.sarif_tool):
                raise SchemaError('--sarif-check and --sarif-tool must be supplied together')
            spec_bytes = args.spec.read_bytes()
            spec = load_run_spec(spec_bytes)
            if spec.mode is not RunMode(args.command):
                raise SchemaError(f'{args.command} command requires mode {args.command}')
            runner = run_diagnose if spec.mode is RunMode.DIAGNOSE else run_write
            started_on = datetime.now(timezone.utc).isoformat()
            manifest, manifest_path, report_path = runner(spec)
            finished_on = datetime.now(timezone.utc).isoformat()
            provenance_path = write_provenance(manifest, manifest_path, spec, spec_bytes=spec_bytes,
                                               started_on=started_on, finished_on=finished_on)
            output = {'run_id': manifest.run_id, 'status': manifest.status.value, 'manifest': str(manifest_path),
                      'report': str(report_path), 'provenance': str(provenance_path)}
            if args.command == 'diagnose' and args.sarif_check:
                capture_args = argparse.Namespace(sarif=None, manifest=manifest_path, repo=None,
                                                  check=args.sarif_check, attempt=1, stream='stdout')
                signals = _import_capture(capture_args)
                sarif_path = manifest_path.parent / 'signals.sarif'
                _write_json(sarif_path, export_sarif(signals, tool_name=args.sarif_tool))
                output['sarif'] = str(sarif_path)
            print(json.dumps(output, sort_keys=True))
            return 0 if manifest.status is ManifestStatus.PASSED else 1
        if args.command == 'import-sarif':
            document = _import_capture(args)
            _write_json(args.output, document)
            print(json.dumps({'signals': str(args.output), 'signal_count': len(document['signals'])}, sort_keys=True))
            return 0
        if args.command == 'export-sarif':
            document = export_sarif(_read_json(args.signals), tool_name=args.tool)
            _write_json(args.output, document)
            print(json.dumps({'sarif': str(args.output), 'run_count': len(document['runs'])}, sort_keys=True))
            return 0
        if args.command == 'mutation-audit':
            from .mutation import run_mutation_audit
            spec = load_run_spec(_read_json(args.spec))
            if spec.mode is RunMode.DIAGNOSE:
                raise SchemaError('mutation-audit requires a write-mode spec')
            audit = run_mutation_audit(spec)
            _write_json(args.output, audit)
            print(json.dumps({'output': str(args.output), 'counts': audit['counts']}, sort_keys=True))
            return 0
        if args.command == 'rank-hotspots':
            document = decode_json(_read_json(args.input))
            if isinstance(document, dict) and document.get('kind') == 'tool-signals':
                document = load_signals(document)
            else:
                # Keep every required semantic judgment in validated findings.
                load_findings(document)
                document = document if isinstance(document, list) else document['findings']
            ranked = rank_hotspots(document, args.repo, lookback_days=args.lookback_days, revision=args.revision)
            _write_json(args.output, ranked)
            print(json.dumps({'ranked': str(args.output), 'history': ranked['history']}, sort_keys=True))
            return 0
        manifest, store = _validated_manifest(args.manifest)
        findings = load_findings(_read_json(args.findings))
        validate_findings(manifest, findings, store)
        print(json.dumps({'valid': True, 'finding_count': len(findings), 'manifest_status': manifest.status.value}, sort_keys=True))
        return 0
    except (SchemaError, ValueError, OSError, RuntimeError) as exc:
        print(f'anti-slop: {exc}', file=sys.stderr)
        return 2
