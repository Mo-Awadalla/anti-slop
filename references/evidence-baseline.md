# Anti-Slop Evidence Baseline

This reference defines the minimum evidence required before the P0 skill may describe a repository risk or a clean result. It is a compact operational summary, not a universal slop score.

## Core rule

Do not automate taste. Search for unjustified cost, missing evidence, mismatched context, and unsafe assumptions.

A signal is not a finding by itself. A finding must connect:

1. an observed signal;
2. repository-specific contextual evidence;
3. a plausible predicted cost or risk;
4. a confidence level;
5. a counterargument or falsifier;
6. a concrete remediation and verification step.

## Risk classes

### Style

Formatting, naming, or organization preferences are not engineering defects unless the repository provides an explicit convention or the difference creates a demonstrated cost. Report these as conventions or questions, not blockers.

### Maintainability

Use evidence such as duplicated behavior, difficult-to-isolate dependencies, unclear ownership, excessive change surface, or tests that cannot exercise the relevant behavior. Explain the cost in this repository rather than applying a universal threshold.

### Behavior and security

Prioritize evidence of incorrect behavior, unsafe input handling, missing authorization or validation, data loss, nondeterminism, resource exhaustion, or verification gaps. State the observed path and the remaining uncertainty.

## Baseline checks

A baseline records what was true before any proposed change:

- source Git root, HEAD, branch, and dirty state;
- relevant project instructions and canonical check candidates;
- exact tokenized checks selected for the run;
- exit code, stdout, stderr, duration, and artifact references for every attempt;
- whether a check was unavailable, skipped, failed, flaky, or not run.

A pre-existing failure remains a failure. Diagnosis must not imply that it was caused by the current run or that it was fixed.

A pass/fail or fail/pass rerun is `flaky`, not passed. Missing or tampered evidence invalidates a pass claim.

## No-edit decision

“No edit is correct” is valid only when:

- the source repository was clean and remained unchanged;
- the required checks completed in the disposable sandbox;
- all required attempts exited zero with verified artifacts;
- no actionable, evidence-backed findings remain.

An empty findings list alone is not evidence of correctness.

## Operational finding mapping

The JSON contract uses compact operational names for the evidence concepts:

- `path`, `line`, and `column` provide the optional **location**;
- `severity` identifies the risk level and should be used with a category in the finding title/source when needed;
- `source` and `evidence_refs` identify the observed evidence and its provenance;
- `impact` records the predicted cost or risk;
- `confidence` records uncertainty;
- `counterargument` records the false-positive case or falsifier;
- `recommended_action` must include a concrete remediation or verification step.

The check record and artifact references provide the verification context. A finding is not trusted merely because its prose fields are present; its source check and evidence references must also validate.

## Evidence limitations

P0 does not provide tamper-proof storage against the same operating-system user, language-specific static analysis, a universal maintainability metric, or automatic execution of commands copied from README or CI text. Discovered commands are candidates only; they require an explicit tokenized run specification.

The source research and blueprint remain the rationale for this baseline. This file intentionally records only stable operational principles so that future agents can load the skill without importing the full research corpus.
