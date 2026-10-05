"""Public command-line interface for diagnosis, bounded writes and findings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .diagnose import run_diagnose
from .findings import validate_findings
from .manifest import validate_manifest_artifacts
from .models import ManifestStatus, RunMode
from .schema import SchemaError, load_findings, load_run_manifest, load_run_spec
from .artifacts import ArtifactStore
from .write_modes import run_write

P0_SUBCOMMANDS = ('diagnose', 'validate-findings')
RUN_SUBCOMMANDS = ('diagnose', 'refactor', 'repair-slop')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='anti-slop')
    subparsers = parser.add_subparsers(dest='command', required=True)
    for name in RUN_SUBCOMMANDS:
        command = subparsers.add_parser(name, help='run explicit checks' if name == 'diagnose' else 'validate supplied bounded edits in an isolated snapshot')
        command.add_argument('--spec', required=True, type=Path)
    findings = subparsers.add_parser('validate-findings', help='validate findings against a manifest')
    findings.add_argument('--manifest', required=True, type=Path)
    findings.add_argument('--findings', required=True, type=Path)
    return parser


def _read_json(path: Path):
    try:
        # Keep JSON text intact so the contract loaders can reject duplicate
        # keys and nonstandard constants before converting it to a mapping.
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        raise SchemaError(f'cannot read JSON {path}: {exc}') from exc


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in RUN_SUBCOMMANDS:
            spec = load_run_spec(_read_json(args.spec))
            if spec.mode is not RunMode(args.command):
                raise SchemaError(f'{args.command} command requires mode {args.command}')
            runner = run_diagnose if spec.mode is RunMode.DIAGNOSE else run_write
            manifest, manifest_path, report_path = runner(spec)
            print(json.dumps({'run_id': manifest.run_id, 'status': manifest.status.value, 'manifest': str(manifest_path), 'report': str(report_path)}, sort_keys=True))
            return 0 if manifest.status is ManifestStatus.PASSED else 1
        manifest_path = args.manifest.resolve()
        manifest = load_run_manifest(_read_json(manifest_path))
        store = ArtifactStore(manifest.run_id)
        store.root = manifest_path.parent
        validate_manifest_artifacts(manifest, store)
        findings = load_findings(_read_json(args.findings))
        validate_findings(manifest, findings, store)
        print(json.dumps({'valid': True, 'finding_count': len(findings), 'manifest_status': manifest.status.value}, sort_keys=True))
        return 0
    except (SchemaError, ValueError, OSError, RuntimeError) as exc:
        print(f'anti-slop: {exc}', file=sys.stderr)
        return 2
