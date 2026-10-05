"""On-demand oracle sensitivity for explicitly supplied, bounded mutations."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import uuid

from .models import AttemptStatus, ManifestStatus, RunMode, RunSpec
from .write_modes import run_write


_RESOURCE_FAILURES = (
    b'timed out', b'output limit', b'memoryerror', b'cannot allocate memory',
    b'resource temporarily unavailable', b'file size limit', b'file too large',
    b'too many open files', b'resource limit',
)


def _outcome(manifest, audit, artifact_root: Path) -> str:
    if audit.get('baseline', {}).get('status') != 'passed' or not audit.get('source_unchanged'):
        return 'inconclusive'
    if manifest.status is ManifestStatus.PASSED and audit.get('completed'):
        return 'survived'
    phases = audit.get('steps', [])
    if len(phases) != 1 or phases[0].get('status') != 'rolled_back':
        return 'inconclusive'
    if not phases[0].get('check_ids'):
        return 'inconclusive'
    records = [record for record in manifest.checks if record.check_id in phases[0]['check_ids']]
    failed = []
    for record in records:
        statuses = {attempt.status for attempt in record.attempts}
        if statuses not in ({AttemptStatus.PASSED}, {AttemptStatus.FAILED}):
            return 'inconclusive'
        for attempt in record.attempts:
            if attempt.status is AttemptStatus.FAILED:
                if attempt.exit_code is None or attempt.exit_code <= 0 or attempt.exit_code >= 125:
                    return 'inconclusive'
                stderr = (artifact_root / attempt.stderr_artifact.path).read_bytes().lower()
                if any(marker in stderr for marker in _RESOURCE_FAILURES):
                    return 'inconclusive'
                failed.append(attempt)
    return 'detected' if failed else 'inconclusive'


def run_mutation_audit(spec: RunSpec, *, hermes_home: str | None = None) -> dict:
    if spec.mode not in (RunMode.REFACTOR, RunMode.REPAIR_SLOP) or not spec.steps:
        raise ValueError('mutation-audit requires a bounded write specification with supplied mutation steps')
    if spec.limits is None or len(spec.steps) > spec.limits.max_steps:
        raise ValueError('mutation count exceeds the declared max_steps budget')
    results = []
    for step in spec.steps:
        snapshot = Path(spec.snapshot_root).with_name(Path(spec.snapshot_root).name + '-' + uuid.uuid4().hex)
        checks = tuple(replace(check, cwd=str(snapshot / Path(check.cwd).relative_to(spec.snapshot_root)))
                       if Path(check.cwd).is_absolute() else check for check in spec.checks)
        single = replace(spec, snapshot_root=str(snapshot), checks=checks, steps=(step,))
        manifest, manifest_path, _ = run_write(single, hermes_home=hermes_home)
        audit_path = manifest_path.parent / 'write/evidence.json'
        audit = json.loads(audit_path.read_text())
        outcome = _outcome(manifest, audit, manifest_path.parent)
        results.append({'id': step.id, 'outcome': outcome, 'paths': [change.path for change in step.changes],
                        'manifest': str(manifest_path), 'evidence': str(audit_path),
                        'snapshot': str(snapshot), 'stop_reason': manifest.stop_reason})
    counts = Counter(item['outcome'] for item in results)
    return {'schema_version': 1, 'kind': 'oracle-sensitivity', 'mutations': results,
            'counts': {key: counts[key] for key in ('detected', 'survived', 'inconclusive')},
            'limitations': [
                'Each supplied mutant is checked independently against the same clean baseline.',
                'Detected means stable check failures, not proof of complete oracle coverage.',
                'Survivors require contextual review; semantic equivalence is not decided.',
                'Timeouts, resource failures, invalid edits and unavailable execution are inconclusive.',
                'No mutation-score threshold or automatic repair is enforced.',
            ]}
