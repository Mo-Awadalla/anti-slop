"""Finding validation and no-edit correctness rules."""

from __future__ import annotations

import re
from typing import Iterable, Optional

from .models import Finding, FindingSeverity, RunManifest
from .schema import SchemaError, load_findings


_VAGUE = re.compile(r"^(?:fix(?:\s+it)?|address(?:\s+this)?|improve(?:\s+it)?|clean(?:\s+this)?\s+up|make\s+better|handle\s+this|resolve\s+this)[.!]?$", re.I)


def validate_findings(manifest: RunManifest, findings: Iterable[Finding], store=None) -> tuple[Finding, ...]:
    values = tuple(findings)
    checks = {record.check_id: record for record in manifest.checks}
    artifact_refs = {ref.path for ref in manifest.artifacts}
    seen: set[str] = set()
    for finding in values:
        if finding.id in seen:
            raise SchemaError(f"duplicate finding id: {finding.id}")
        seen.add(finding.id)
        if finding.source not in checks:
            raise SchemaError(f"finding source is not a declared check: {finding.source}")
        if not finding.evidence_refs:
            raise SchemaError(f"finding {finding.id} has no evidence_refs")
        source_refs = {
            ref.path for attempt in checks[finding.source].attempts
            for ref in (attempt.stdout_artifact, attempt.stderr_artifact) if ref is not None
        }
        for ref in finding.evidence_refs:
            if ref not in artifact_refs:
                raise SchemaError(f"finding {finding.id} references unknown evidence: {ref}")
            if ref not in source_refs:
                raise SchemaError(f"finding {finding.id} references evidence from another source: {ref}")
            if store is not None and not store.verify(next(a for a in manifest.artifacts if a.path == ref)):
                raise SchemaError(f"finding {finding.id} references unverifiable evidence: {ref}")
        if _VAGUE.fullmatch(finding.recommended_action):
            raise SchemaError(f"finding {finding.id} has a vague or unsupported recommended_action")
    return values


def findings_from_json(value) -> tuple[Finding, ...]:
    return load_findings(value)


def is_no_edit_correct(manifest: RunManifest, findings: Iterable[Finding]) -> bool:
    from .manifest import derive_manifest_status
    from .models import ManifestStatus, RunMode
    return (
        manifest.mode is RunMode.DIAGNOSE
        and manifest.discovery is not None and not manifest.discovery.dirty
        and derive_manifest_status(manifest.checks, stop_reason=manifest.stop_reason,
                                   artifact_paths={a.path for a in manifest.artifacts}) is ManifestStatus.PASSED
        and not any(f.severity is not FindingSeverity.INFO for f in findings)
    )
