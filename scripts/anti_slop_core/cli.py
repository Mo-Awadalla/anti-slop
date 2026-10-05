"""Public P0 command-line interface; intentionally no write-mode commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .diagnose import run_diagnose
from .findings import validate_findings
from .manifest import validate_manifest_artifacts
from .schema import SchemaError, load_findings, load_run_manifest, load_run_spec
from .artifacts import ArtifactStore

P0_SUBCOMMANDS = ("diagnose", "validate-findings")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anti-slop")
    subparsers = parser.add_subparsers(dest="command", required=True)
    diagnose = subparsers.add_parser("diagnose", help="run read-only checks in Bubblewrap")
    diagnose.add_argument("--spec", required=True, type=Path)
    findings = subparsers.add_parser("validate-findings", help="validate findings against a manifest")
    findings.add_argument("--manifest", required=True, type=Path)
    findings.add_argument("--findings", required=True, type=Path)
    return parser


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"cannot read JSON {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "diagnose":
            spec = load_run_spec(_read_json(args.spec))
            manifest, manifest_path, report_path = run_diagnose(spec)
            print(json.dumps({"run_id": manifest.run_id, "status": manifest.status.value, "manifest": str(manifest_path), "report": str(report_path)}, sort_keys=True))
            return 0
        manifest_path = args.manifest.resolve()
        manifest = load_run_manifest(_read_json(manifest_path))
        store = ArtifactStore(manifest.run_id)
        store.root = manifest_path.parent
        validate_manifest_artifacts(manifest, store)
        findings = load_findings(_read_json(args.findings))
        validate_findings(manifest, findings, store)
        print(json.dumps({"valid": True, "finding_count": len(findings), "manifest_status": manifest.status.value}, sort_keys=True))
        return 0
    except (SchemaError, ValueError, OSError, RuntimeError) as exc:
        print(f"anti-slop: {exc}", file=sys.stderr)
        return 2
