# Anti-Slop

An agent skill for preventing unnecessary complexity, diagnosing code-quality risks, and performing bounded, evidence-backed refactoring or repair. It judges code against project intent and behavior, with counterarguments and meaningful checks; AI authorship or disliked style is not evidence of harm.

The skill is the main product. Read [`SKILL.md`](SKILL.md) for the workflow and [`references/agent-workflow.md`](references/agent-workflow.md) for code-changing work. Guidance works with ordinary repository tools. The optional Python runner provides reproducible evidence and verifies supplied changes in an isolated snapshot.

## Implemented workflows

- **Prevent:** preserve requested behavior and existing boundaries; inspect generated additions for unjustified cost.
- **Diagnose:** report contextual risks without editing, distinguishing style, maintenance, and behavior/security evidence.
- **Refactor:** make coherent behavior-preserving changes with independent oracles and recovery points.
- **Repair:** verify the intended correction and unaffected contracts, retaining pre-existing failures and uncertainty.

The runner exposes `diagnose`, `refactor`, `repair-slop`, and `validate-findings`. Write modes consume supplied full-text changes, check a green baseline and each step, enforce path/diff bounds and immutable oracles, recover failed steps, and export a replay-verified patch. Snapshots include tracked source only. Check output and process resources are bounded. Every mode leaves the source checkout unchanged.

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

The optional `import-sarif`, `export-sarif`, and `rank-hotspots` commands normalize tool signals and rank review attention without inventing contextual findings or changing severity. `mutation-audit` checks explicitly supplied mutants independently and reports detected, surviving, or inconclusive outcomes without a score threshold. Run CLI outputs also include unsigned in-toto/SLSA provenance. Neither tool signals nor unsigned provenance certify correctness or authenticated execution.

`diagnose --sarif-check scanner --sarif-tool ToolName` exports the selected recorded check's SARIF stdout. The manual [SARIF workflow](.github/workflows/sarif-interchange.yml) can run a committed diagnosis spec or normalize a committed capture, with an optional separate upload job.

For a non-Linux host with Docker, build and run the bounded Linux environment:

```bash
docker build -t anti-slop-runtime:local .
python3 scripts/container.py test
python3 scripts/container.py run --spec run.json --snapshot /tmp/task-snapshots --evidence /tmp/task-evidence
python3 scripts/container.py exec --evidence /tmp/e2e-evidence -- /usr/bin/python3 e2e.py --output /evidence/run
```

The container runs nonroot, with no network or added capabilities, read-only source, and cgroup limits. Nested Bubblewrap requires explicit Docker seccomp and masked-proc exceptions. Read the operating contract for those tradeoffs and unsupported-host behavior.


## Validation and research

The agent workflow, real-repository pilot, and bounded write-mode phases are implemented. [`Acceptance results`](research/acceptance-results.md) records current Docker/Bubblewrap regression, resource, and CLI end-to-end evidence alongside historical runs. [`Pilot results`](research/pilot-results.md) documents the original trust defects and friction. [`Skill evaluation`](research/skill-evaluation.md) records qualitative decisions and the later original-versus-revised comparison, including the caught baseline-instruction regression.

The preserved practitioner research and blueprint remain unchanged in [`research/`](research/README.md). They are rationale, not an implemented-feature checklist or proof that the skill improves agent outcomes. Missing original reports and unperformed paired model/corpus effectiveness studies remain explicit. No universal slop score is used.

From `scripts/`, run `python3 -m unittest discover -s tests -v`. Real sandbox tests explicitly skip when isolation is unavailable; those skips do not establish isolation. See the operating contract for compilation and real-run checks.
