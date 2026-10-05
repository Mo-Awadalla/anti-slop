# Anti-Slop

A Hermes skill for finding unjustified code complexity and quality risks without mistaking personal style for engineering evidence.

## Status

**In progress.** The current implementation is a read-only diagnostic foundation, not the finished anti-slop workflow. It includes a Hermes skill, a Python runner, evidence schemas, sandboxing, and finding validation. The public CLI currently exposes `diagnose` and `validate-findings`; it does not edit code.

The main unfinished work is to make the agent-facing skill the product: guide useful, contextual code-quality judgment during implementation and review, while keeping the runner as optional support. There is no automatic finding generation, no new-code prevention workflow, and no `refactor` or `repair-slop` mode yet.

## What to finish next

1. Refocus `SKILL.md` around practical agent behavior: inspect context, distinguish style from real cost or risk, give evidence-backed findings with counterarguments, and preserve required behavior.
2. Pilot the workflow on a real repository. Judge whether the findings are useful, whether false positives are controlled, and how much user effort the workflow takes.
3. Rework the roadmap from those results. Consider a fast path or reusable repository profiles only if the pilot shows they save time without weakening the result.
4. Treat code-changing refactor or repair modes as separate future work. Define authorization, scope, behavior-preservation evidence, recovery, and end-to-end acceptance before exposing them.

See [`references/p1-p3-roadmap.md`](references/p1-p3-roadmap.md) for the current handoff. The old staged P1–P3 sequence was stale because the P0 runner already included sandboxing, evidence capture, and manifest handling.

## Current boundary

- Read-only with respect to the target repository.
- Checks must be explicitly specified; repository text is not executed as a command source.
- No universal “slop score” or style-only findings.
- No automatic edits, refactoring, or repair.
- No unsandboxed fallback when required isolation is unavailable.

## Repository layout

- `SKILL.md` — agent workflow and safety boundary.
- `references/` — evidence baseline, operating contract, and remaining-work roadmap.
- `scripts/` — diagnostic runner and its implementation.
- `templates/` — run and finding schemas.

## Research artifacts

The preserved practitioner research and implementation blueprint are in [`research/`](research/README.md). The concise skill-blueprint notes are in [`deep-research-skills`](https://github.com/Mo-Awadalla/deep-research-skills/blob/master/deep-research-briefs/references/anti-slop-skill-blueprint-notes.md). The earlier full research-report files were not present in the cache when this repository was prepared; see the research index for that gap.

## CLI quick check

From the repository root:

```bash
python3 scripts/run.py --help
python3 scripts/run.py diagnose --help
python3 scripts/run.py validate-findings --help
```

The runner uses Python's standard library. A real diagnosis also requires Git and Linux Bubblewrap (`bwrap`). See `SKILL.md` and `references/operating-contract.md` before using it.
