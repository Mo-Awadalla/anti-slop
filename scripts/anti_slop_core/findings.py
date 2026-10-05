"""Finding validation and no-edit correctness rules."""

from __future__ import annotations

import re
from typing import Iterable, Optional

from .models import Finding, FindingSeverity, RunManifest
from .schema import SchemaError, load_findings


_VAGUE = re.compile(r"^(?:fix(?:\s+it)?|address(?:\s+this)?|improve(?:\s+it)?|clean(?:\s+this)?\s+up|make\s+better|handle\s+this|resolve\s+this)[.!]?$", re.I)
_UNSUPPORTED = re.compile(r"\b(?:refactor|repair-slop|rewrite\s+the\s+file|delete\s+the\s+file|run\s+arbitrary)\b", re.I)


def validate_findings(manifest: RunManifest, findings: Iterable[Finding], store=None) -> tuple[Finding, ...]:
    values = tuple(findings)
    check_ids = {record.check_id for record in manifest.checks}
    artifact_refs = {ref.path for ref in manifest.artifacts}
    seen: set[str] = set()
    for finding in values:
        if finding.id in seen:
            raise SchemaError(f"duplicate finding id: {finding.id}")
        seen.add(finding.id)
        if finding.source not in check_ids:
            raise SchemaError(f"finding source is not a declared check: {finding.source}")
        if not finding.evidence_refs:
            raise SchemaError(f"finding {finding.id} has no evidence_refs")
        for ref in finding.evidence_refs:
            if ref not in artifact_refs:
                raise SchemaError(f"finding {finding.id} references unknown evidence: {ref}")
            if store is not None and not store.verify(next(a for a in manifest.artifacts if a.path == ref)):
                raise SchemaError(f"finding {finding.id} references unverifiable evidence: {ref}")
        if _VAGUE.fullmatch(finding.recommended_action) or _UNSUPPORTED.search(finding.recommended_action):
            raise SchemaError(f"finding {finding.id} has a vague or unsupported recommended_action")
    return values


def findings_from_json(value) -> tuple[Finding, ...]:
    return load_findings(value)


def is_no_edit_correct(manifest: RunManifest, findings: Iterable[Finding]) -> bool:
    return manifest.status.value == "passed" and not any(f.severity is not FindingSeverity.INFO for f in findings)
