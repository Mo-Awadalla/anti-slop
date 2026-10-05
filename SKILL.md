---
name: anti-slop
description: Use when applying the evidence-first anti-slop workflow to diagnose repository risks or validate supplied findings without editing the target repository.
version: 1.1.0
author: Mohamed
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [software-development, code-quality, anti-slop]
    related_skills: []
---

# Anti-Slop

## Overview

This user-local skill provides a controlled, evidence-first workflow for diagnosing inefficient, unreadable, difficult-to-test, or unsafe code. P0 is read-only with respect to the target repository. It separates mechanical evidence capture from contextual judgment and does not turn taste into fact.

## When to use

Use this skill when the request asks whether code is unnecessarily complex, hard to test, risky to maintain, or otherwise “sloppy,” and the answer should be grounded in the actual repository.

Do not use it as a universal style checker, a replacement for project-specific instructions, or permission to edit code. P0 does not support automatic refactoring or repair.

## P0 Boundary

The P0 CLI exposes exactly two subcommands:

- `diagnose --spec PATH`
- `validate-findings --manifest PATH --findings PATH`

`refactor` and `repair-slop` are intentionally not exposed. Diagnosis captures Git ground truth, creates a detached snapshot, runs explicitly supplied checks inside Bubblewrap, records stdout/stderr artifacts with SHA-256 and size metadata, derives manifest status, and renders a Markdown report. Unsupported ecosystems receive generic reduced-capability reporting rather than guessed language-specific findings.

P0 does not mutate the source repository, generate subjective style findings, or claim a passed run when required checks are unavailable, blocked, flaky, failed, or unverified.

## Required workflow

1. Understand the request and identify the requested outcome.
2. Inspect repository instructions and establish scope without editing.
3. Define the objective, paths, and exact tokenized checks.
4. Preview or validate the run specification before execution.
5. Invoke the deterministic runner against a clean detached snapshot.
6. Analyze contextual risks using the evidence baseline.
7. Validate every finding and its evidence references.
8. Render the report with blockers, uncertainty, and the next safe step.

Read [references/evidence-baseline.md](references/evidence-baseline.md) before making contextual claims. Read [references/operating-contract.md](references/operating-contract.md) before extending the implementation.

## Risk classes

- **Style:** convention or taste. Do not present it as an engineering defect without explicit repository evidence.
- **Maintainability:** change surface, duplication, ownership, isolation, or testability costs supported by repository context.
- **Behavior/security:** observed incorrectness, unsafe assumptions, validation gaps, authorization issues, data loss, nondeterminism, or resource risks.

Core rule: **Do not automate taste. Search for unjustified cost, missing evidence, mismatched context, and unsafe assumptions.**

## Finding format

A validated finding should communicate:

`signal -> contextual evidence -> predicted cost -> confidence -> counterargument/falsifier -> remediation/verification`

Every finding must identify its source and evidence references. Vague directives such as “clean this up” are not actionable findings. A counterargument is required so likely false positives remain visible.

## Prohibitions

- No universal slop score or arbitrary repository-independent thresholds.
- No arbitrary execution of commands copied from README or CI text.
- No shell interpolation, unsandboxed fallback, or hidden network access.
- No success claim from prose alone or from an asserted status field.
- No automatic edits in P0.
- No claim that a pre-existing failing baseline was fixed.
- No claim of correctness when required evidence is missing, flaky, unavailable, failed, skipped, or tampered with.

## Completion checklist

Before reporting a clean result:

- [ ] Source repository was inspected and was clean at discovery.
- [ ] Exact tokenized checks were explicitly selected.
- [ ] Checks ran only in the disposable snapshot and Bubblewrap sandbox.
- [ ] Every attempt has captured, independently verifiable artifacts.
- [ ] Manifest status is derived rather than accepted from input.
- [ ] Findings and evidence references validate.
- [ ] Report status agrees with the manifest.
- [ ] “No edit is correct” is used only when all required checks pass and no actionable findings remain.

## Verification

From the `scripts/` directory, run:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q run.py anti_slop_core tests
python3 run.py --help
```

For a real smoke run, provide a clean Git repository and a JSON run spec with absolute `repo_path` and `snapshot_root`, `mode: diagnose`, and explicit tokenized checks. Verify the emitted `manifest.json`, `report.md`, artifact hashes, and source-repository immutability before trusting the result.

P1–P3 remain deferred. See [references/p1-p3-roadmap.md](references/p1-p3-roadmap.md).
