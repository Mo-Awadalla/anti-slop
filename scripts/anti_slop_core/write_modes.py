"""Apply finite supplied text edits to a disposable snapshot with evidence gates.

This module never generates edits, runs codemods, changes the source checkout,
weakens a failing baseline, or claims that supplied checks prove all behavior.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, replace
from pathlib import Path

from .adapters import select_adapter
from .artifacts import ArtifactStore
from .checkpoint import Checkpoint
from .checks import run_checks, unavailable_checks
from .diff_budget import (
    DiffGuardError, analyze_diff, apply_step, guard_diff, read_tree,
    directory_state, tree_sha256, unified_patch,
)
from .discovery import DiscoveryError, DirtySourceError, create_snapshot, discover, source_fingerprint
from .manifest import derive_check_status, derive_manifest_status, validate_manifest_artifacts, write_manifest
from .models import CheckStatus, RunManifest, RunMode, RunSpec
from .report import render_report
from .sandbox import BubblewrapSandbox, SandboxUnavailable
from .schema import load_run_spec


def _validated_spec(spec: RunSpec) -> RunSpec:
    if spec.mode not in (RunMode.REFACTOR, RunMode.REPAIR_SLOP):
        raise ValueError('run_write requires refactor or repair-slop mode')
    # Programmatic callers receive the same strict guards as JSON/CLI callers.
    payload = asdict(spec)
    return load_run_spec(json.dumps(payload))


def _phase_checks(spec: RunSpec, prefix: str):
    return tuple(replace(check, id=prefix + ':' + check.id, required=True, rerun=True) for check in spec.checks)


def _all_green(records, artifacts, store) -> bool:
    paths = {artifact.path for artifact in artifacts}
    return bool(records) and all(store.verify(ref) for ref in artifacts) and all(
        derive_check_status(record, artifact_paths=paths) is CheckStatus.PASSED for record in records)


def _phase(spec: RunSpec, prefix: str, sandbox, store):
    checks = _phase_checks(spec, prefix)
    if sandbox is None:
        return unavailable_checks(checks, store, 'sandbox unavailable; write verification cannot run')
    return run_checks(checks, sandbox, store)


def _require_oracles(spec: RunSpec, tree) -> None:
    for path in spec.oracle_paths:
        state = tree.get(path)
        if state is None or not state.data:
            raise DiffGuardError(f'oracle_paths must name existing nonempty regular files: {path}')


def _verification_inputs(spec: RunSpec, tree) -> tuple[str, ...]:
    """Protect discoverable local argv files; imported helpers remain explicit."""
    root = Path(spec.snapshot_root).resolve()
    result = set(spec.oracle_paths) | set(spec.protected_paths)
    for check in spec.checks:
        cwd = Path(check.cwd)
        base = cwd if cwd.is_absolute() else root / cwd
        for argument in check.argv:
            if argument.startswith('-'):
                continue
            item = Path(argument)
            candidate = item if item.is_absolute() else base / item
            try:
                relative = candidate.resolve().relative_to(root).as_posix()
            except (ValueError, OSError):
                continue
            if relative in tree:
                result.add(relative)
    return tuple(sorted(result))


def run_write(spec: RunSpec, *, hermes_home: str | None = None, run_id: str | None = None) -> tuple[RunManifest, Path, Path]:
    spec = _validated_spec(spec)
    run_id = run_id or 'run-' + uuid.uuid4().hex
    store = ArtifactStore(run_id, hermes_home)
    setup_discovery = discover(spec.repo_path)
    store.assert_outside(setup_discovery.git_root, spec.snapshot_root)
    store.create()
    records = []
    artifacts = []
    discovery = None
    stop_reason = None
    adapter_summary = None
    baseline_tree = None
    last_green_tree = None
    source_before = None
    cumulative_files = set()
    cumulative_lines = 0
    evidence = {
        'schema_version': 1, 'mode': spec.mode.value, 'objective': spec.objective,
        'behavior_budget': spec.behavior_budget,
        'oracle_checks': list(spec.oracle_checks), 'oracle_paths': list(spec.oracle_paths),
        'allowed_paths': list(spec.allowed_paths), 'protected_paths': list(spec.protected_paths),
        'limits': asdict(spec.limits), 'baseline': {'status': 'not-run', 'check_ids': []},
        'steps': [], 'completed': False, 'no_edit': False, 'source_unchanged': False,
        'final_changes': None, 'cumulative_changed_lines': 0, 'final_patch_artifact': None,
        'verification_limit': 'Only the supplied immutable oracles and checks were verified; coverage adequacy remains a review decision.',
    }
    try:
        discovery = setup_discovery
        if discovery.dirty:
            raise DirtySourceError('source repository is dirty; write run stopped before checks')
        source_before = source_fingerprint(discovery.git_root)
        create_snapshot(discovery, spec.snapshot_root)
        baseline_tree = read_tree(spec.snapshot_root)
        baseline_directories = directory_state(spec.snapshot_root)
        last_green_tree = baseline_tree
        _require_oracles(spec, baseline_tree)
        verification_inputs = _verification_inputs(spec, baseline_tree)
        evidence['effective_protected_paths'] = list(verification_inputs)
        if set(spec.allowed_paths) & set(verification_inputs):
            raise DiffGuardError('allowed_paths overlaps a check command input; verification files are immutable')
        adapter_summary = select_adapter(spec.snapshot_root).summary()
        try:
            sandbox = BubblewrapSandbox(spec.snapshot_root)
        except SandboxUnavailable:
            sandbox = None
        with Checkpoint.capture_snapshot(spec.snapshot_root) as checkpoint:
            try:
                phase_records, phase_artifacts = _phase(spec, 'baseline', sandbox, store)
            except (OSError, ValueError, RuntimeError):
                checkpoint.rollback()
                raise
            records.extend(phase_records)
            artifacts.extend(phase_artifacts)
            try:
                checks_changed_snapshot = (read_tree(spec.snapshot_root) != baseline_tree
                                           or directory_state(spec.snapshot_root) != baseline_directories)
            except DiffGuardError:
                checks_changed_snapshot = True
            if checks_changed_snapshot:
                checkpoint.rollback()
                evidence['baseline'] = {'status': 'rolled_back', 'check_ids': [record.check_id for record in phase_records]}
                raise DiffGuardError('baseline checks modified the snapshot; changes rolled back')
        baseline_passed = _all_green(phase_records, phase_artifacts, store)
        evidence['baseline'] = {'status': 'passed' if baseline_passed else 'failed',
                                'check_ids': [record.check_id for record in phase_records],
                                'tree_sha256': tree_sha256(baseline_tree),
                                'outcomes': {record.check_id: derive_check_status(record).value for record in phase_records}}
        if not baseline_passed:
            raise DiffGuardError('baseline must pass every supplied check without flaky, missing or unavailable results; no steps applied')
        for index, step in enumerate(spec.steps, start=1):
            before_step = read_tree(spec.snapshot_root)
            step_evidence = {'id': step.id, 'description': step.description, 'status': 'rejected',
                             'check_ids': [], 'changes': None,
                             'before_tree_sha256': tree_sha256(before_step), 'after_tree_sha256': None}
            evidence['steps'].append(step_evidence)
            with Checkpoint.capture_snapshot(spec.snapshot_root) as checkpoint:
                try:
                    apply_step(spec.snapshot_root, step, allowed_paths=spec.allowed_paths,
                               protected_paths=verification_inputs)
                    after_step = read_tree(spec.snapshot_root)
                    after_directories = directory_state(spec.snapshot_root)
                    diff = guard_diff(before_step, after_step, allowed_paths=spec.allowed_paths,
                                      protected_paths=verification_inputs, limits=spec.limits)
                    guard_diff(baseline_tree, after_step, allowed_paths=spec.allowed_paths,
                               protected_paths=verification_inputs, limits=spec.limits)
                    prospective_files = cumulative_files | {entry['path'] for entry in diff['entries']}
                    if len(prospective_files) > spec.limits.max_files:
                        raise DiffGuardError('cumulative diff exceeds max_files')
                    if cumulative_lines + diff['changed_lines'] > spec.limits.max_changed_lines:
                        raise DiffGuardError('cumulative diff exceeds max_changed_lines')
                    if not diff['entries']:
                        raise DiffGuardError('step has no content change; omit it and use steps=[] for a verified no-edit result')
                    step_evidence['changes'] = diff
                    step_evidence['after_tree_sha256'] = tree_sha256(after_step)
                    phase_records, phase_artifacts = _phase(spec, f'step-{index}', sandbox, store)
                    records.extend(phase_records)
                    artifacts.extend(phase_artifacts)
                    step_evidence['check_ids'] = [record.check_id for record in phase_records]
                    step_evidence['outcomes'] = {record.check_id: derive_check_status(record).value for record in phase_records}
                    if read_tree(spec.snapshot_root) != after_step or directory_state(spec.snapshot_root) != after_directories:
                        raise DiffGuardError('verification checks modified the snapshot')
                    if not _all_green(phase_records, phase_artifacts, store):
                        raise DiffGuardError('step checks did not pass every supplied check without flaky, missing or unavailable results')
                    step_evidence['status'] = 'passed'
                    cumulative_files = prospective_files
                    cumulative_lines += diff['changed_lines']
                    last_green_tree = after_step
                except (DiffGuardError, OSError, ValueError, RuntimeError) as exc:
                    checkpoint.rollback()
                    restored = read_tree(spec.snapshot_root)
                    if restored != before_step:
                        raise RuntimeError('failed-step rollback integrity check failed') from exc
                    step_evidence['status'] = 'rolled_back'
                    step_evidence['reason'] = str(exc)
                    step_evidence['restored_tree_sha256'] = tree_sha256(restored)
                    raise DiffGuardError(f'step {step.id} rolled back to the previous green checkpoint: {exc}') from exc
        if read_tree(spec.snapshot_root) != last_green_tree:
            raise DiffGuardError('snapshot changed after the last verified checkpoint')
        evidence['completed'] = True
    except (DiscoveryError, DiffGuardError, OSError, ValueError, RuntimeError) as exc:
        stop_reason = str(exc)
    finally:
        if discovery is not None and source_before is not None:
            try:
                evidence['source_unchanged'] = source_before == source_fingerprint(discovery.git_root)
                if not evidence['source_unchanged']:
                    evidence['completed'] = False
                    stop_reason = 'source repository content changed during write verification; no final patch exported'
            except (DiscoveryError, OSError) as exc:
                evidence['completed'] = False
                stop_reason = f'cannot verify source integrity: {exc}'
    if baseline_tree is not None and last_green_tree is not None:
        evidence['final_changes'] = analyze_diff(baseline_tree, last_green_tree)
        evidence['cumulative_changed_lines'] = cumulative_lines
        evidence['no_edit'] = evidence['completed'] and not evidence['final_changes']['entries']
    if evidence['completed'] and evidence['source_unchanged']:
        patch = store.put_bytes('write/final.patch', unified_patch(baseline_tree, last_green_tree), 'text/x-diff')
        artifacts.append(patch)
        evidence['final_patch_artifact'] = patch.path
    evidence['stop_reason'] = stop_reason
    audit_ref = store.put_bytes('write/evidence.json', (json.dumps(evidence, indent=2, sort_keys=True) + '\n').encode('utf-8'), 'application/json')
    artifacts.append(audit_ref)
    status = derive_manifest_status(records, stop_reason=stop_reason, artifact_paths={ref.path for ref in artifacts})
    manifest = RunManifest(run_id, spec.mode, spec.repo_path, spec.snapshot_root, status,
                           tuple(records), (), tuple(artifacts), discovery, stop_reason)
    validate_manifest_artifacts(manifest, store)
    manifest_path = store.root / 'manifest.json'
    report_path = store.root / 'report.md'
    write_manifest(manifest_path, manifest)
    # render_report's optional evidence hook is integrated by the core reporter.
    report_path.write_text(render_report(manifest, adapter_summary=adapter_summary, write_evidence=evidence), encoding='utf-8')
    return manifest, manifest_path, report_path
