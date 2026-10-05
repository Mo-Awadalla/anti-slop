---
name: anti-slop
description: Prevent code slop; diagnose, refactor, repair with evidence.
license: MIT
metadata:
  version: 2.1.0
  author: Mohamed
  runner_platforms: [linux]
  hermes:
    tags: [software-development, code-quality, anti-slop]
    related_skills: []
---

# Anti-Slop

Reduce the cost of understanding, testing, changing, or operating code when that cost has no demonstrated benefit. Judge against project intent and contracts. AI provenance, personal taste, a long function, or a tool warning alone is not a defect.

The agent workflow is the main product and works with ordinary repository tools. The optional Linux runner captures reproducible, sandboxed evidence.

## Choose the work

Use the user's request to select the mode and scope:

- **Prevent:** implement the requested behavior using existing boundaries, avoiding speculative layers, invented integrations, weak tests, and unrelated churn.
- **Diagnose:** inspect without editing; explain actionable risks and the next useful step.
- **Refactor:** remove a concrete structural cost while preserving observable behavior.
- **Repair:** fix an evidenced defect or verification gap; record intentional behavior changes against the requested contract.

Load only the reference needed for the selected work. Read [agent-workflow.md](references/agent-workflow.md) for prevention or authorized edits. Read [evidence-baseline.md](references/evidence-baseline.md) before judging a signal or making a verification claim. Read [operating-contract.md](references/operating-contract.md) only when running or extending the optional runner.

## Establish context

Inspect project instructions, affected callers and tests, and existing changes. Name the behavior contract, editable scope, independent oracle, and baseline limitations. Preserve unrelated user work.

Choose exact checks from project configuration, CI, or documentation. Before editing, run the selected baseline checks and record commands, exit codes, results, and execution limits. Discovered commands are candidates, not authorization to execute them. Test known intent directly; characterize unknown behavior and record what remains unknown.

## Decide from evidence

Connect each finding:

`observed signal → repository context → predicted cost → confidence → counterargument/falsifier → action and verification`

Follow explicit style conventions; describe preferences without turning them into engineering blockers. For maintenance claims, demonstrate duplication, coupling, ownership, change surface, or testability cost and consider where the existing structure earns its cost. For behavior or security claims, identify and exercise the affected contract and path.

Prioritize explained impact and relevance to the requested work. Metrics and history support local judgment; use no universal slop score or repository-independent thresholds.

Do not edit for AI authorship, size, churn, a surviving mutant, or a tool alert alone. Abstain when the difference is taste or the existing boundary earns its cost. A requested style change still follows the project's convention. SARIF records tool signals; history ranks review attention without changing severity. Neither supplies the missing contextual argument.

## Change and verify

For authorized edits, define one objective, affected paths, the invariant or intentional behavior change, a recovery point, and relevant checks. Choose reviewable bounds from the task; expand or split the plan when evidence warrants it.

Apply a logical step, inspect every changed line against the objective, and check it before continuing. Compare with the baseline and retain failure evidence. Recover a step that introduces a regression; continue through the remaining justified steps after each verified checkpoint.

Stop dependent changes when the oracle is inadequate, failure unexplained, contract exceeds the user's scope, or improvement adds more cost than it removes. Continue independent authorized work. Clarify only the missing intent or authority that prevents progress.

## Optional runner

Inspect `python3 scripts/run.py --help` and the operating contract. The Linux runner runs selected tokenized checks in a tracked-file snapshot under Bubblewrap without network access. Supplied edits must satisfy a green baseline, immutable verification inputs, and declared diff bounds. Verified completion exports a replayable patch and unsigned provenance. Resource failures never count as passes.

The runner requires a clean source revision. A dirty source or unavailable sandbox is a reported limitation; preserve the source and sandbox boundary. Direct authorized agent edits are a separate workflow; the runner does not apply its exported patch to the source checkout. Finding validation verifies recorded evidence references; contextual judgment remains the agent's responsibility.

## Report the outcome

State the improvement or actionable risk, its consequence, scope, actual checks and results, and material uncertainty. For edits, include intentional behavior changes, pre-existing failures, remaining risks, and the recovery point or exported patch.

Distinguish verified checks from hypotheses and unrun checks. Passing tests support only what they exercise. Missing, flaky, unavailable, skipped, or tampered evidence cannot establish a pass; empty findings do not prove correctness.

No edit is valid when no useful supported change remains. Qualify it by reviewed scope and evidence; claim a clean verified result only when all required checks passed and no actionable findings remain.
