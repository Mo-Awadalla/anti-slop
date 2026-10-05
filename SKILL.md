---
name: anti-slop
description: Prevent code slop; diagnose, refactor, repair with evidence.
license: MIT
metadata:
  version: 2.0.0
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

Read [agent-workflow.md](references/agent-workflow.md) for prevention or code-changing work, including characterization and recovery. Read [evidence-baseline.md](references/evidence-baseline.md) before judging a signal or making a verification claim. Read [operating-contract.md](references/operating-contract.md) when using or extending the runner.

## Establish context

Inspect project instructions, relevant callers and tests, and current working changes. Identify the required outputs, errors, side effects, ordering, permissions, persistence, and public interfaces. Preserve unrelated user work; choose an isolated checkout when needed.

Select relevant checks from project configuration, CI, and documentation and record actual baseline results. Discovered commands are candidates; deliberately choose exact commands and an appropriate execution environment.

Continue when the target, behavior contract, existing changes, verification oracle, and baseline limitations are explicit. Test known intent directly. Characterize unknown behavior and identify what remains unknown.

## Decide from evidence

Connect each finding:

`observed signal → repository context → predicted cost → confidence → counterargument/falsifier → action and verification`

Follow explicit style conventions; describe preferences without turning them into engineering blockers. For maintenance claims, demonstrate duplication, coupling, ownership, change surface, or testability cost and consider where the existing structure earns its cost. For behavior or security claims, identify and exercise the affected contract and path.

Prioritize explained impact and relevance to the requested work. Metrics and history support local judgment; use no universal slop score or repository-independent thresholds.

## Change and verify

For authorized edits, define one objective, affected paths, the invariant or intentional behavior change, a recovery point, and relevant checks. Choose reviewable bounds from the task; expand or split the plan when evidence warrants it.

Apply a logical step, inspect every changed line against the objective, and check it before continuing. Compare with the baseline and retain failure evidence. Recover a step that introduces a regression; continue through the remaining justified steps after each verified checkpoint.

Stop dependent changes when the oracle is inadequate, failure unexplained, contract exceeds the user's scope, or improvement adds more cost than it removes. Continue independent authorized work. Clarify only the missing intent or authority that prevents progress.

## Optional runner

Inspect `python3 scripts/run.py --help` and the operating contract. Diagnosis runs selected tokenized checks in a disposable snapshot under Bubblewrap without network access. Refactor and repair consume supplied change steps, enforce declared scope and diff bounds, check the baseline and each step, and recover failed steps. Verified completion exports a reviewable patch. All modes leave the source repository unchanged.

The runner requires a clean source revision. A dirty source or unavailable sandbox is a reported limitation; preserve the source and sandbox boundary. Direct authorized agent edits are a separate workflow; the runner does not apply its exported patch to the source checkout. Finding validation verifies recorded evidence references; contextual judgment remains the agent's responsibility.

## Report the outcome

State the improvement or actionable risk, its consequence, scope, actual checks and results, and material uncertainty. For edits, include intentional behavior changes, pre-existing failures, remaining risks, and the recovery point or exported patch.

Distinguish verified checks from hypotheses and unrun checks. Passing tests support only what they exercise. Missing, flaky, unavailable, skipped, or tampered evidence cannot establish a pass; empty findings do not prove correctness.

No edit is valid when no useful supported change remains. Qualify it by reviewed scope and evidence; claim a clean verified result only when all required checks passed and no actionable findings remain.
