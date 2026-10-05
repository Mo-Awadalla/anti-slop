# Anti-Slop: Phase Completion

The earlier P0 runner already provided diagnosis, artifact capture, sandboxing, and findings validation. The remaining roadmap focused on making the skill useful, piloting it, and adding bounded code-changing execution. These phases are now implemented.

| Phase | Delivered | Evidence |
| --- | --- | --- |
| P1 — Agent workflow | Prevention, contextual diagnosis, refactor and repair routing; independent verification; scoped recovery; concise entrypoint and conditional references written using Matt's skill-writing guidance | [SKILL.md](../SKILL.md), [agent workflow](agent-workflow.md), [qualitative evaluation](../research/skill-evaluation.md) |
| P2 — Pilot and friction | Read-only diagnosis of upstream anti-slop, three reproduced trust defects with counterarguments and verified capture provenance; source unchanged | [Pilot results](../research/pilot-results.md) and recorded captures |
| P3 — Supplied changes and recovery | Executable refactor and repair-slop snapshot modes; declared objective/oracles/bounds; baseline and per-step checks; rollback; patch export; strict CLI/spec/manifest contracts | [Operating contract](operating-contract.md), [acceptance results](../research/acceptance-results.md) |

The pilot supported keeping the runner optional. No reusable check profiles or extra fast-path machinery were added: the agent workflow already works without a run spec, and one pilot does not establish that profiles save enough effort to justify their maintenance.

## Completion boundaries

The direct agent workflow covers intentional defect repair and preservation. The deterministic runner's two write modes both require a green baseline and preserve behavior; they edit only supplied text in a disposable snapshot, not the source checkout. The runner does not generate findings/edits, establish assertion independence automatically, or certify semantic equivalence. This is a deliberate implemented boundary, not an unimplemented command placeholder.

Preserved blueprint proposals for language-specific codemods, automated metrics, external scan adapters, signed evidence, and red-to-green runner repair are extensions, not shipped claims. Generic explicit checks can invoke available project tools inside the sandbox, subject to its runtime/network limits.

## Empirical questions

Local tests, real Bubblewrap CLI runs, one upstream pilot, and qualitative skill scenarios establish concrete execution behavior and useful decisions. They do not establish a general improvement in maintainability, hidden regression rate, review time, or agent outcomes. A paired corpus study with clean controls and independent outcome measurement is required for those claims. Missing research reports remain documented in the research index.
