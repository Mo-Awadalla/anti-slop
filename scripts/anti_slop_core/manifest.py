"""Derived manifest status and serialization helpers."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional, Set

from .models import (
    ArtifactRef, AttemptStatus, CheckRecord, CheckStatus, CommandAttempt,
    DiscoveryInfo, Finding, ManifestStatus, RunManifest, RunMode,
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
            refs = (attempt.stdout_artifact, attempt.stderr_artifact)
            if any(ref is None for ref in refs):
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
    for record in manifest.checks:
        if derive_check_status(record) is not CheckStatus.PASSED:
            continue
        for attempt in record.attempts:
            for ref in (attempt.stdout_artifact, attempt.stderr_artifact):
                if ref is None or ref.path not in by_path or not store.verify(ref):
                    raise ValueError(f"passed check has an unverified artifact: {record.check_id}")
