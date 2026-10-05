"""Deterministic Markdown reporting from validated models only."""

from __future__ import annotations

from .findings import is_no_edit_correct
from .models import Finding, RunManifest


def render_report(manifest: RunManifest, findings: tuple[Finding, ...] | None = None, adapter_summary: dict | None = None) -> str:
    values = tuple(manifest.findings if findings is None else findings)
    lines = ["# Anti-Slop Diagnose Report", "", f"- Run: `{manifest.run_id}`", f"- Status: **{manifest.status.value}**", f"- Repository: `{manifest.repo_path}`", f"- Snapshot: `{manifest.snapshot_root}`", ""]
    if manifest.stop_reason:
        lines.extend([f"## Stopped", "", manifest.stop_reason, ""])
    if manifest.discovery:
        d = manifest.discovery
        lines.extend(["## Discovery", "", f"- Git root: `{d.git_root}`", f"- HEAD: `{d.head}`", f"- Branch: `{d.branch}`", f"- Dirty at discovery: **{d.dirty}**", f"- Command candidates discovered (not executed): {len(d.candidates)}", ""])
    if adapter_summary:
        lines.extend(["## Adapter capabilities", "", "```json", __import__("json").dumps(adapter_summary, indent=2, sort_keys=True), "```", ""])
    lines.extend(["## Checks", "", "| Check | Required | Derived status | Attempts |", "|---|---:|---|---:|"])
    for record in manifest.checks:
        lines.append(f"| `{record.check_id}` | {record.required} | **{record.status.value}** | {len(record.attempts)} |")
    if not manifest.checks:
        lines.extend(["", "**Gap:** no checks were supplied; the run cannot establish project health."])
    lines.extend(["", "## Findings", ""])
    if values:
        for finding in values:
            lines.extend([f"### {finding.id}: {finding.title}", "", f"- Source: `{finding.source}`", f"- Severity: **{finding.severity.value}**", f"- Impact: {finding.impact}", f"- Confidence: {finding.confidence:.2f}", f"- Recommended action: {finding.recommended_action}", f"- Counterargument: {finding.counterargument}", f"- Evidence: {', '.join('`' + ref + '`' for ref in finding.evidence_refs)}", ""])
    else:
        lines.append("No findings were supplied. This is not evidence of correctness unless every required check passed.")
        lines.append("")
    if is_no_edit_correct(manifest, values):
        lines.extend(["## Decision", "", "**No edit is correct:** all required checks passed and there are no actionable findings.", ""])
    else:
        lines.extend(["## Decision", "", "No-edit correctness is **not established**. Resolve the check/finding gaps above before treating the run as clean.", ""])
    lines.extend(["## Evidence integrity", "", f"Declared artifacts: {len(manifest.artifacts)}. Each artifact must be independently hash- and size-verified before trusting a pass.", ""])
    return "\n".join(lines)
