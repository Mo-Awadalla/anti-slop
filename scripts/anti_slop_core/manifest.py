"""Derived manifest status and serialization helpers."""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import asdict
from enum import Enum
import tempfile
from pathlib import Path
from typing import Iterable, Optional, Set

from .models import (
    ArtifactRef, AttemptStatus, CheckRecord, CheckStatus, CommandAttempt,
    DiscoveryInfo, Finding, ManifestStatus, RunManifest, RunMode,
)
from .diff_budget import (
    DiffGuardError, analyze_diff, read_tree, replay_patch,
    tree_identities, tree_sha256,
)


def new_run_id() -> str:
    return uuid.uuid4().hex


def _attempt_outcome(attempt: CommandAttempt) -> str:
    if attempt.status is AttemptStatus.UNAVAILABLE:
        return "unavailable"
    if attempt.status in (AttemptStatus.BLOCKED, AttemptStatus.SKIPPED, AttemptStatus.NOT_RUN):
        return attempt.status.value
    if attempt.status is AttemptStatus.PASSED and attempt.exit_code == 0:
        return "passed"
    if attempt.status is AttemptStatus.FAILED or attempt.exit_code not in (None, 0):
        return "failed"
    return attempt.status.value


def derive_check_status(record: CheckRecord, *, artifact_paths: Optional[Set[str]] = None) -> CheckStatus:
    """Derive status solely from attempts; input status is never consulted."""
    if not record.attempts:
        return CheckStatus.NOT_RUN
    for attempt in record.attempts:
        if attempt.status is AttemptStatus.PASSED:
            if not attempt.sandboxed:
                return CheckStatus.FAILED
            refs = (attempt.stdout_artifact, attempt.stderr_artifact)
            if any(ref is None or ref.sha256 is None or ref.size_bytes is None for ref in refs):
                return CheckStatus.FAILED
            if artifact_paths is not None and any(ref.path not in artifact_paths for ref in refs):
                return CheckStatus.FAILED
    outcomes = [_attempt_outcome(a) for a in record.attempts]
    if "unavailable" in outcomes:
        return CheckStatus.UNAVAILABLE
    if "blocked" in outcomes:
        return CheckStatus.BLOCKED
    if "skipped" in outcomes:
        return CheckStatus.SKIPPED
    if len(set(outcomes)) > 1 and {"passed", "failed"}.issubset(set(outcomes)):
        return CheckStatus.FLAKY
    if all(outcome == "passed" for outcome in outcomes):
        return CheckStatus.PASSED
    return CheckStatus.FAILED


def derive_manifest_status(records: Iterable[CheckRecord], *, stop_reason: Optional[str] = None, artifact_paths: Optional[Set[str]] = None) -> ManifestStatus:
    if stop_reason:
        return ManifestStatus.STOPPED
    statuses = [derive_check_status(r, artifact_paths=artifact_paths) for r in records if r.required]
    if not statuses:
        return ManifestStatus.FAILED
    if any(status is CheckStatus.BLOCKED or status is CheckStatus.UNAVAILABLE for status in statuses):
        return ManifestStatus.BLOCKED
    if any(status is CheckStatus.FLAKY for status in statuses):
        return ManifestStatus.FLAKY
    if all(status is CheckStatus.PASSED for status in statuses):
        return ManifestStatus.PASSED
    return ManifestStatus.FAILED


def artifact_to_dict(ref: ArtifactRef) -> dict:
    return {key: value for key, value in {"path": ref.path, "sha256": ref.sha256, "size_bytes": ref.size_bytes, "media_type": ref.media_type}.items() if value is not None}


def attempt_to_dict(attempt: CommandAttempt) -> dict:
    data = {"check_id": attempt.check_id, "argv": list(attempt.argv), "cwd": attempt.cwd, "status": attempt.status.value, "exit_code": attempt.exit_code, "duration_ms": attempt.duration_ms, "sandboxed": attempt.sandboxed}
    data["stdout_artifact"] = artifact_to_dict(attempt.stdout_artifact) if attempt.stdout_artifact else None
    data["stderr_artifact"] = artifact_to_dict(attempt.stderr_artifact) if attempt.stderr_artifact else None
    return data


def check_to_dict(record: CheckRecord) -> dict:
    return {"check_id": record.check_id, "status": derive_check_status(record).value, "required": record.required, "attempts": [attempt_to_dict(a) for a in record.attempts], "finding_ids": list(record.finding_ids)}


def finding_to_dict(finding: Finding) -> dict:
    data = {"id": finding.id, "title": finding.title, "source": finding.source, "evidence_refs": list(finding.evidence_refs), "severity": finding.severity.value, "impact": finding.impact, "confidence": finding.confidence, "recommended_action": finding.recommended_action, "counterargument": finding.counterargument}
    for key, value in (("path", finding.path), ("line", finding.line), ("column", finding.column)):
        if value is not None:
            data[key] = value
    return data


def discovery_to_dict(info: Optional[DiscoveryInfo]) -> Optional[dict]:
    if info is None:
        return None
    return {"git_root": info.git_root, "head": info.head, "branch": info.branch, "dirty": info.dirty, "candidates": list(info.candidates)}


def manifest_to_dict(manifest: RunManifest) -> dict:
    status = derive_manifest_status(manifest.checks, stop_reason=manifest.stop_reason, artifact_paths={a.path for a in manifest.artifacts})
    data = {"run_id": manifest.run_id, "mode": manifest.mode.value, "repo_path": manifest.repo_path, "snapshot_root": manifest.snapshot_root, "status": status.value, "checks": [check_to_dict(c) for c in manifest.checks], "findings": [finding_to_dict(f) for f in manifest.findings], "artifacts": [artifact_to_dict(a) for a in manifest.artifacts]}
    if manifest.discovery is not None:
        data["discovery"] = discovery_to_dict(manifest.discovery)
    if manifest.stop_reason:
        data["stop_reason"] = manifest.stop_reason
    return data


def write_manifest(path: str | Path, manifest: RunManifest) -> None:
    target = Path(path)
    target.write_text(json.dumps(manifest_to_dict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_manifest_artifacts(manifest: RunManifest, store) -> None:
    """Verify every declared artifact and every pass attempt's two captures."""
    for ref in manifest.artifacts:
        if not store.verify(ref):
            raise ValueError(f"artifact verification failed: {ref.path}")
    by_path = {ref.path: ref for ref in manifest.artifacts}
    if len(by_path) != len(manifest.artifacts):
        raise ValueError("manifest contains duplicate artifact paths")
    for record in manifest.checks:
        for attempt in record.attempts:
            for ref in (attempt.stdout_artifact, attempt.stderr_artifact):
                if ref is None or ref.path not in by_path or ref != by_path[ref.path] or not store.verify(ref):
                    raise ValueError(f"check has an unverified artifact: {record.check_id}")
    if manifest.mode in (RunMode.REFACTOR, RunMode.REPAIR_SLOP):
        try:
            _validate_write_evidence(manifest, store, by_path)
        except (TypeError, KeyError, AttributeError, UnicodeError) as exc:
            raise ValueError("write evidence has an invalid structure") from exc


def _validate_write_evidence(manifest: RunManifest, store, by_path: dict) -> None:
    audit = by_path.get("write/evidence.json")
    if audit is None:
        raise ValueError("write manifest requires verified write/evidence.json")
    try:
        evidence = json.loads(store.read(audit))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("write evidence must be valid JSON") from exc
    if not isinstance(evidence, dict) or evidence.get("schema_version") != 2 or evidence.get("mode") != manifest.mode.value:
        raise ValueError("write evidence mode or schema is inconsistent")
    if evidence.get("stop_reason") != manifest.stop_reason:
        raise ValueError("write evidence stop reason is inconsistent")
    derived = derive_manifest_status(manifest.checks, stop_reason=manifest.stop_reason,
                                     artifact_paths=set(by_path))
    if derived is not ManifestStatus.PASSED:
        if evidence.get("completed") is True or evidence.get("final_patch_artifact") is not None:
            raise ValueError("incomplete write run cannot claim completion or export a final patch")
        return
    if evidence.get("completed") is not True or evidence.get("source_unchanged") is not True:
        raise ValueError("passed write run requires completed, unchanged-source evidence")
    if not manifest.discovery or manifest.discovery.dirty:
        raise ValueError("passed write run requires a clean discovered revision")
    if evidence.get("behavior_budget") != "preserve" or not evidence.get("objective"):
        raise ValueError("write evidence requires a preservation objective")
    if evidence.get("final_patch_artifact") != "write/final.patch" or "write/final.patch" not in by_path:
        raise ValueError("passed write run requires a verified final.patch artifact")
    baseline, steps = evidence.get("baseline"), evidence.get("steps")
    if not isinstance(baseline, dict) or baseline.get("status") != "passed" or not isinstance(steps, list):
        raise ValueError("passed write run requires a passed baseline and step sequence")
    records = {record.check_id: record for record in manifest.checks}
    visited = set()
    phases = [("baseline", baseline)] + [(f"step-{index}", step) for index, step in enumerate(steps, 1)]
    base_ids = baseline.get("check_ids", [])
    if not base_ids or any(not isinstance(identifier, str) or not identifier.startswith("baseline:") for identifier in base_ids):
        raise ValueError("write baseline check identities are inconsistent")
    base_suffixes = {identifier.removeprefix("baseline:") for identifier in base_ids}
    oracles = evidence.get("oracle_checks", [])
    if not oracles or not set(oracles).issubset(base_suffixes) or not evidence.get("oracle_paths"):
        raise ValueError("write evidence requires declared immutable verification oracles")
    previous_tree = baseline.get("tree_sha256")
    for prefix, phase in phases:
        if not isinstance(phase, dict) or phase.get("status") != "passed":
            raise ValueError("passed write run contains an unverified step")
        ids = phase.get("check_ids", [])
        if set(ids) != {prefix + ":" + suffix for suffix in base_suffixes} or len(ids) != len(set(ids)):
            raise ValueError("write phases must run the complete baseline check set")
        for identifier in ids:
            record = records.get(identifier)
            if record is None or not record.required or len(record.attempts) != 2 or derive_check_status(record, artifact_paths=set(by_path)) is not CheckStatus.PASSED:
                raise ValueError("write evidence references an unverified required check")
            if phase.get("outcomes", {}).get(identifier) != "passed":
                raise ValueError("write evidence check outcome is inconsistent")
        visited.update(ids)
        if prefix != "baseline":
            if phase.get("before_tree_sha256") != previous_tree:
                raise ValueError("write checkpoint chain is inconsistent")
            previous_tree = phase.get("after_tree_sha256")
    if visited != set(records):
        raise ValueError("write manifest checks disagree with the recorded phases")
    changes = evidence.get("final_changes")
    if not isinstance(changes, dict) or not isinstance(changes.get("entries"), list):
        raise ValueError("write evidence requires the final diff record")
    entries = changes["entries"]
    if changes.get("files") != len(entries) or evidence.get("no_edit") is not (not entries):
        raise ValueError("write final diff and no-edit decision disagree")
    allowed = set(evidence.get("allowed_paths", []))
    protected = set(evidence.get("oracle_paths", [])) | set(evidence.get("protected_paths", [])) | set(evidence.get("effective_protected_paths", []))
    paths = [entry.get("path") for entry in entries]
    if len(paths) != len(set(paths)) or any(path not in allowed or path in protected for path in paths):
        raise ValueError("write export contains undeclared or protected paths")
    _validate_patch_replay(evidence, baseline, steps, store, by_path)


def _materialize_baseline(root: Path, data: bytes) -> dict:
    try:
        encoded = json.loads(data)
        if not isinstance(encoded, dict):
            raise ValueError("baseline tree must be an object")
        for path, state in encoded.items():
            # Baseline names may contain spaces; edited patch paths may not.
            if not isinstance(path, str) or not path or path.startswith('/') or any(part in ('', '.', '..', '.git') for part in path.split('/')):
                raise ValueError("unsafe baseline tree path")
            if not isinstance(state, dict) or set(state) != {'content_base64', 'mode'}:
                raise ValueError("invalid baseline file state")
            mode = state['mode']
            if type(mode) is not int or not 0 <= mode <= 0o7777:
                raise ValueError("invalid baseline file mode")
            content = base64.b64decode(state['content_base64'], validate=True)
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(content)
            target.chmod(mode)
        return read_tree(root)
    except (OSError, TypeError, UnicodeError, ValueError) as exc:
        raise ValueError(f"invalid replay baseline: {exc}") from exc


def _validate_patch_replay(evidence, baseline, steps, store, by_path) -> None:
    baseline_path = baseline.get('tree_artifact')
    if baseline_path != 'write/baseline-tree.json' or baseline_path not in by_path:
        raise ValueError("write evidence requires exported baseline bytes")
    baseline_data = store.read(by_path[baseline_path])
    try:
        with tempfile.TemporaryDirectory(prefix='anti-slop-verifier-') as directory:
            root = Path(directory)
            initial = _materialize_baseline(root, baseline_data)
            if tree_sha256(initial) != baseline.get('tree_sha256') or tree_identities(initial) != baseline.get('identities'):
                raise ValueError("exported baseline bytes/modes disagree with recorded identity")
            current = initial
            for index, step in enumerate(steps, 1):
                path = f'write/step-{index}.patch'
                if step.get('patch_artifact') != path or path not in by_path:
                    raise ValueError("write step requires an exported replay patch")
                if tree_sha256(current) != step.get('before_tree_sha256'):
                    raise ValueError("replayed checkpoint chain disagrees")
                replayed = replay_patch(root, store.read(by_path[path]))
                if tree_sha256(replayed) != step.get('after_tree_sha256') or tree_identities(replayed) != step.get('identities'):
                    raise ValueError("replayed step bytes/modes disagree with recorded identity")
                if analyze_diff(current, replayed) != step.get('changes'):
                    raise ValueError("replayed step disagrees with recorded diff")
                protected = set(evidence.get('effective_protected_paths', [])) | set(evidence.get('oracle_paths', [])) | set(evidence.get('protected_paths', []))
                allowed = set(evidence.get('allowed_paths', []))
                if any(entry['path'] not in allowed or entry['path'] in protected for entry in step['changes']['entries']):
                    raise ValueError("replayed step changes undeclared or protected paths")
                current = replayed
            if tree_sha256(current) != evidence.get('final_tree_sha256') or tree_identities(current) != evidence.get('final_identities'):
                raise ValueError("replayed final tree disagrees with recorded identity")
            if analyze_diff(initial, current) != evidence.get('final_changes'):
                raise ValueError("replayed final diff disagrees with recorded changes")
            expected = current
        # Replay the actual public export independently of the step sequence.
        with tempfile.TemporaryDirectory(prefix='anti-slop-export-verifier-') as directory:
            root = Path(directory)
            _materialize_baseline(root, baseline_data)
            actual = replay_patch(root, store.read(by_path['write/final.patch']))
            if actual != expected:
                raise ValueError("exported patch does not reproduce recorded final bytes/modes")
    except (DiffGuardError, OSError) as exc:
        raise ValueError(f"write patch replay failed: {exc}") from exc
