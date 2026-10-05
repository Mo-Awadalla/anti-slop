"""Orchestrate one read-only diagnose run."""

from __future__ import annotations

import uuid
from pathlib import Path

from .adapters import select_adapter
from .artifacts import ArtifactStore
from .checks import run_checks, unavailable_checks
from .discovery import DiscoveryError, DirtySourceError, create_snapshot, discover, source_fingerprint
from .manifest import derive_manifest_status, validate_manifest_artifacts, write_manifest
from .models import RunManifest, RunSpec
from .report import render_report
from .sandbox import BubblewrapSandbox, SandboxUnavailable


def _new_run_id() -> str:
    return "run-" + uuid.uuid4().hex


def _persist(store: ArtifactStore, manifest: RunManifest, adapter_summary: dict | None = None) -> tuple[Path, Path]:
    manifest_path = store.root / "manifest.json"
    report_path = store.root / "report.md"
    write_manifest(manifest_path, manifest)
    report_path.write_text(render_report(manifest, adapter_summary=adapter_summary), encoding="utf-8")
    return manifest_path, report_path


def run_diagnose(spec: RunSpec, *, hermes_home: str | None = None, run_id: str | None = None) -> tuple[RunManifest, Path, Path]:
    run_id = run_id or _new_run_id()
    store = ArtifactStore(run_id, hermes_home)
    store.create()
    discovery = None
    records = ()
    artifacts = ()
    stop_reason = None
    adapter_summary = None
    try:
        discovery = discover(spec.repo_path)
        if discovery.dirty:
            raise DirtySourceError("source repository is dirty; execution stopped before checks")
        before = source_fingerprint(discovery.git_root)
        create_snapshot(discovery, spec.snapshot_root)
        adapter = select_adapter(spec.snapshot_root)
        adapter_summary = adapter.summary()
        try:
            sandbox = BubblewrapSandbox(spec.snapshot_root)
            records, artifacts = run_checks(spec.checks, sandbox, store)
        except SandboxUnavailable as exc:
            records, artifacts = unavailable_checks(spec.checks, store, f"sandbox unavailable: {exc}")
        after = source_fingerprint(discovery.git_root)
        if before != after:
            stop_reason = "source repository content changed during diagnosis; result stopped"
    except DirtySourceError as exc:
        stop_reason = str(exc)
    except DiscoveryError as exc:
        stop_reason = str(exc)
    except OSError as exc:
        stop_reason = f"diagnosis setup failed: {exc}"
    status = derive_manifest_status(records, stop_reason=stop_reason, artifact_paths={a.path for a in artifacts})
    manifest = RunManifest(run_id, spec.mode, spec.repo_path, spec.snapshot_root, status, tuple(records), (), tuple(artifacts), discovery, stop_reason)
    validate_manifest_artifacts(manifest, store)
    manifest_path, report_path = _persist(store, manifest, adapter_summary)
    return manifest, manifest_path, report_path
