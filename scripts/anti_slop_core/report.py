"""Deterministic Markdown reporting from validated models only."""

from __future__ import annotations

import json

from .findings import is_no_edit_correct
from .manifest import derive_check_status, derive_manifest_status
from .models import Finding, RunManifest


def render_report(manifest: RunManifest, findings: tuple[Finding, ...] | None = None, adapter_summary: dict | None = None, write_evidence: dict | None = None) -> str:
    values = tuple(manifest.findings if findings is None else findings)
    status = derive_manifest_status(manifest.checks, stop_reason=manifest.stop_reason, artifact_paths={a.path for a in manifest.artifacts})
    lines = ["# Anti-Slop " + manifest.mode.value.title() + " Report", "", f"- Run: `{manifest.run_id}`", f"- Check status: **{status.value}**", f"- Repository: `{manifest.repo_path}`", f"- Snapshot: `{manifest.snapshot_root}`", ""]
    if manifest.stop_reason:
        lines.extend([f"## Stopped", "", manifest.stop_reason, ""])
    if manifest.discovery:
        d = manifest.discovery
        lines.extend(["## Discovery", "", f"- Git root: `{d.git_root}`", f"- HEAD: `{d.head}`", f"- Branch: `{d.branch}`", f"- Dirty at discovery: **{d.dirty}**", f"- Command candidates discovered (not executed): {len(d.candidates)}", ""])
    if adapter_summary:
        lines.extend(["## Adapter capabilities", "", "```json", json.dumps(adapter_summary, indent=2, sort_keys=True), "```", ""])
    lines.extend(["## Checks", "", "| Check | Required | Derived status | Attempts |", "|---|---:|---|---:|"])
    for record in manifest.checks:
        lines.append(f"| `{record.check_id}` | {record.required} | **{derive_check_status(record).value}** | {len(record.attempts)} |")
    if not manifest.checks:
        lines.extend(["", "**Gap:** no checks were supplied; the run cannot establish project health."])
    lines.extend(["", "## Command attempts", ""])
    for record in manifest.checks:
        for index, attempt in enumerate(record.attempts, 1):
            lines.extend([
                f"- `{record.check_id}` attempt {index}: argv `{json.dumps(list(attempt.argv))}`",
                f"  - cwd `{attempt.cwd}`; exit `{attempt.exit_code}`; status `{attempt.status.value}`; sandboxed `{attempt.sandboxed}`; duration `{attempt.duration_ms}` ms",
            ])
            for label, ref in (("stdout", attempt.stdout_artifact), ("stderr", attempt.stderr_artifact)):
                if ref is not None:
                    lines.append(f"  - [{label}]({ref.path}) SHA-256 `{ref.sha256}`; {ref.size_bytes} bytes")
    if write_evidence is not None:
        lines.extend([
            "", "## Supplied change sequence", "",
            f"- Objective: {write_evidence.get('objective', '')}",
            f"- Behavior budget: `{write_evidence.get('behavior_budget', '')}`",
            f"- Completed: **{write_evidence.get('completed', False)}**",
            f"- Source unchanged: **{write_evidence.get('source_unchanged', False)}**",
            f"- Verification oracle checks: `{json.dumps(write_evidence.get('oracle_checks', []))}`",
            f"- Baseline: `{json.dumps(write_evidence.get('baseline', {}), sort_keys=True)}`",
            "", "| Step | Outcome | Changed files | Changed lines |", "|---|---|---|---:|",
        ])
        for step in write_evidence.get("steps", []):
            changes = step.get("changes") or {}
            paths = [entry['path'] for entry in changes.get('entries', [])]
            lines.append(f"| `{step.get('id', '')}` | {step.get('status', '')} | `{json.dumps(paths)}` | {changes.get('changed_lines', 0)} |")
            if step.get("reason"):
                lines.extend(["", f"Step `{step['id']}`: {step['reason']}", ""])
            if step.get("status") == "rolled_back":
                lines.extend(["", f"Recovered step `{step['id']}` to tree `{step.get('before_tree_sha256', '')}`.", ""])
        lines.extend(["", f"Final diff: `{json.dumps(write_evidence.get('final_changes', {}), sort_keys=True)}`", ""])
        patch = write_evidence.get("final_patch_artifact")
        if patch:
            lines.extend([f"Reviewable patch: [final.patch]({patch}). Apply only within the authorized task after reviewing its base revision and diff.", ""])
        lines.extend(["The checks establish the selected oracle outcomes. Behavior preservation and maintenance benefit still require contextual review; no universal complexity or coupling metric is inferred.", ""])
    lines.extend(["", "## Findings", ""])
    if values:
        for finding in values:
            lines.extend([f"### {finding.id}: {finding.title}", "", f"- Source: `{finding.source}`", f"- Severity: **{finding.severity.value}**", f"- Impact: {finding.impact}", f"- Confidence: {finding.confidence:.2f}", f"- Recommended action: {finding.recommended_action}", f"- Counterargument: {finding.counterargument}", f"- Evidence: {', '.join('`' + ref + '`' for ref in finding.evidence_refs)}", ""])
    else:
        lines.append("No findings were supplied. This is not evidence of correctness unless every required check passed.")
        lines.append("")
    if write_evidence is not None:
        decision = "Supplied sequence verified; inspect the exported patch." if write_evidence.get("completed") and status.value == "passed" else "Sequence stopped; retained verified work does not establish completion."
        lines.extend(["## Decision", "", decision, ""])
    elif is_no_edit_correct(manifest, values):
        lines.extend(["## Decision", "", "**No edit is correct for the supplied evidence:** all required checks passed and there are no supplied actionable findings. This decision covers the recorded checks; it does not replace contextual review.", ""])
    else:
        lines.extend(["## Decision", "", "No-edit correctness is **not established**. Resolve the check/finding gaps above before treating the run as clean.", ""])
    lines.extend(["## Evidence integrity", "", f"Declared artifacts: {len(manifest.artifacts)}. Each artifact must be independently hash- and size-verified before trusting a pass.", ""])
    return "\n".join(lines)
