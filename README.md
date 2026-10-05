# Anti-Slop

An agent skill for preventing unnecessary complexity, diagnosing code-quality risks, and performing bounded, evidence-backed refactoring or repair. It judges code against project intent and behavior, with counterarguments and meaningful checks; AI authorship or disliked style is not evidence of harm.

The skill is the main product. Read [`SKILL.md`](SKILL.md) for the workflow and [`references/agent-workflow.md`](references/agent-workflow.md) for code-changing work. Guidance works with ordinary repository tools. The optional Python runner provides reproducible evidence and verifies supplied changes in an isolated snapshot.

## Implemented workflows

- **Prevent:** preserve requested behavior and existing boundaries; inspect generated additions for unjustified cost.
- **Diagnose:** report contextual risks without editing, distinguishing style, maintenance, and behavior/security evidence.
- **Refactor:** make coherent behavior-preserving changes with independent oracles and recovery points.
- **Repair:** verify the intended correction and unaffected contracts, retaining pre-existing failures and uncertainty.

The runner exposes `diagnose`, `refactor`, `repair-slop`, and `validate-findings`. Write modes consume explicit full-text change steps, check a green baseline and each step, enforce path/diff bounds and immutable oracles, recover a failed step, and export a verified reviewable patch after completion. Every mode leaves the source checkout unchanged.

Runner `repair-slop` currently handles preservation only. Intentional behavior changes and repairs starting with a failing regression check use the authorized direct agent workflow; the runner does not claim to support that contract. It also does not generate fixes or prove coverage adequacy automatically.

## Use

Place this repository's skill folder where your agent discovers skills, or invoke its instructions explicitly. No Python package installation is needed. The agent guidance is portable; runner execution requires Linux, Git, and working Bubblewrap.

```bash
python3 scripts/run.py --help
python3 scripts/run.py diagnose --spec run.json
python3 scripts/run.py refactor --spec run.json
python3 scripts/run.py repair-slop --spec run.json
python3 scripts/run.py validate-findings --manifest manifest.json --findings findings.json
```

Read the [`operating contract`](references/operating-contract.md) before preparing a spec. It explains inputs, artifact locations, execution limits, and exit codes. Runtime validation is authoritative; JSON schemas live in `templates/`.

## Validation and research

The remaining roadmap's agent workflow, real-repository pilot, and bounded write-mode phases have been implemented. [`Acceptance results`](research/acceptance-results.md) records tested behavior; [`pilot results`](research/pilot-results.md) documents useful findings on the original repository and the observed friction. [`Skill evaluation`](research/skill-evaluation.md) records qualitative clean-control, prevention, repair, and weak-oracle decisions.

The preserved practitioner research and blueprint remain unchanged in [`research/`](research/README.md). They are rationale, not an implemented-feature checklist or proof that the skill improves agent outcomes. Missing original reports and unperformed paired model/corpus effectiveness studies remain explicit. No universal slop score is used.

From `scripts/`, run `python3 -m unittest discover -s tests -v`. Real sandbox tests explicitly skip when isolation is unavailable; those skips do not establish isolation. See the operating contract for compilation and real-run checks.
