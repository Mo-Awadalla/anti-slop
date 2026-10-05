# Acceptance and evaluation boundaries

This document records implementation acceptance for the expanded skill and
runner. It does not replace either preserved research source or claim that a
model evaluation has been performed.

## Reproducing the implementation checks

Run from `scripts/`:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q run.py anti_slop_core tests
python3 run.py --help
```

The suite separates two kinds of evidence:

- Deterministic orchestration tests execute trusted fixture commands in a test
  double against temporary Git repositories. They exercise actual independent
  output assertions and an injected behavior regression. They establish runner
  decisions, patch bounds, checkpoint recovery, source preservation, and
  artifact consistency; they do not establish a security boundary.
- Real Bubblewrap smoke tests first run a successful `/bin/true` probe. They
  then verify that a host file is inaccessible and an external network route is
  absent. A missing or unusable Bubblewrap is an explicit skip with its actual
  diagnostic, never a successful boundary check. Restricted execution on this
  development host initially failed with `NETLINK_ROUTE socket: Operation not
  permitted`; execution outside that outer restriction supports the smoke.

The Python implementation and tests use the standard library only. No Python
package installation is needed. Git and Linux Bubblewrap are external runtime
requirements for repository discovery and actual sandbox execution.

## Behavioral coverage

| Contract | Acceptance evidence |
| --- | --- |
| Diagnose, refactor, repair, and strict explicit inputs | Public CLI/parser and schema tests; missing write contract, unsafe paths, invalid oracles, duplicate steps, and unsupported behavior changes rejected |
| Clean source preservation | Full file/content/mode identity, including Git metadata, compared before and after fixture runs |
| Dirty source | Stops before snapshot execution and preserves the user's edits |
| Green baseline and supplied change | Independent multiplication outputs retained, bounded final patch emitted, manifest parsed by a fresh loader, and artifacts verified |
| Red or flaky baseline | No verified pass, failure classification retained, and supplied production change not applied |
| No checks or unavailable sandbox | Cannot claim pass; no host fallback or verified patch |
| Bounded change | Preimage hash, exact allowed paths, file/line/step budgets, and cumulative file budget exercised; additions/deletions replayed byte-for-byte in a fresh Git checkout, including CRLF, Unicode separators, lone CR, and missing final newline |
| Immutable oracle | Attempt to weaken a test along with a behavior regression rejected |
| Check side effects | A check that modifies source in the disposable snapshot cannot certify the result; snapshot restored |
| Recovery | An injected second-step behavior regression is detected, failed step recovered, and the first verified improvement retained |
| Clean control/no edit | Empty step sequence leaves all production content unchanged |
| Evidence trust | Missing hashes/sizes, altered captures, artifact aliases, unsandboxed attempts, mismatched references, unrelated check evidence, and asserted status rejected |

The arithmetic fixture includes zero, negative, integer, and fractional inputs.
Its oracle is authored independently of the function. Adding one to the result
is deliberately detected during staged verification. This demonstrates local
oracle sensitivity; it is not a general mutation-testing integration.

## Mapping the blueprint's 27 proposed acceptance cases

The blueprint is preserved design research. Its proposed corpus, tools, and
blanket review gates are not all implementation claims. “Automated” below
means a deterministic runner regression test; “workflow” means an instruction
that still needs contextual agent judgment; “unperformed” means no empirical
result is claimed.

| # | Proposed case | Current evidence and limit |
| --- | --- | --- |
| 1 | Clean baseline | Automated discovery, immutable source, exact commands/exit codes, manifest/artifact tests. Candidates are suggested; canonical command selection remains the agent's responsibility. |
| 2 | Dirty tree | Automated dirty-source stop before checks and snapshot creation. The runner never overwrites the source. |
| 3 | Pre-existing failure | Automated red baseline retained and supplied changes withheld. |
| 4 | Unknown command | Automated missing executable, no checks, and unavailable sandbox cannot pass. |
| 5 | High-risk target | Workflow requires the actual affected boundary and targeted checks. No automated auth/payment/migration risk classifier or blanket human-approval gate is claimed. |
| 6 | Legacy characterization | Workflow explains observation and normalization. The hand-authored fixture is sensitive to a defect; automatic harness generation and volatile-field normalization have not been implemented or evaluated. |
| 7 | Golden-master approval | Workflow distinguishes intentional contract changes; runner rejects intentional-change contracts. No golden-master update integration or approval trial has been performed. |
| 8 | Weak generated test | Workflow requires independent assertions and retained boundaries. No automatic semantic detector of self-derived expectations is claimed. |
| 9 | Mutation gate | Automated fixture injects a `+1` behavior mutation and detects it through independent outputs; failed step recovered. General mutation-tool integration and mutation-score studies unperformed. |
| 10 | Property invariant | Fixture covers zero, negative, integer, and fractional boundaries. Generated property exploration has not been performed. |
| 11 | Integration contract | Supplied external contract checks can be selected. No provider/consumer integration fixture or external-system experiment has been performed. |
| 12 | Atomic refactor | Automated real CLI and deterministic fixtures verify one supplied transformation, preserve its oracle, retain snapshot checkpoint evidence, and export a replayable patch. |
| 13 | Scope creep | Automated exact-path and protected verification/configuration/dependency gates. Contextual unrelated formatting detection remains workflow judgment. |
| 14 | Budget breach | Automated file/line/step and cumulative bounds stop and recover. The workflow explains splitting; automatic alternative-plan generation is not provided. |
| 15 | Rollback | Automated second-step failure leaves the first verified change, retains failure captures, and records recovery; actual Bubblewrap/CLI smoke covers this path. |
| 16 | Bisectable sequence | Per-step check IDs and audit localize the deliberately bad step. Snapshot checkpoints are not Git commits; no automatic `git bisect` integration or multi-revision empirical trial is claimed. |
| 17 | Semantic codemod | Workflow supports choosing an existing project tool and reviewing its output. Runner applies supplied finite text changes; no semantic codemod engine is bundled. |
| 18 | Style-only control | Workflow/tabletop review keeps size or preference alone from establishing a defect. Blinded style false-positive model trials unperformed. |
| 19 | Hotspot prioritization | Workflow uses explained impact and available history. No automatic churn/complexity ranking or hotspot comparison study is claimed. |
| 20 | Over-engineering trap | Workflow asks what real boundary or change cost an abstraction serves. No automated cost/benefit inference or comparative model study is claimed. |
| 21 | No metric gaming | Automated immutable oracle files, argv verifier protection, and protected configuration stop several concrete bypasses. Semantic weakness in undeclared tests or metric gaming still requires review; no universal detector is claimed. |
| 22 | Negative tradeoff | Workflow examines coupling, public surface, dependencies, and test weakness. No automatic equivalence or maintainability-tradeoff proof is claimed. |
| 23 | Clean control | Automated empty supplied sequence retains the exact original production content. This establishes no forced runner edit; model abstention rates remain unperformed. |
| 24 | Complete report | Reports/manifest record commands, exits, artifacts, actual file/line changes, baseline, stop and recovered snapshot hashes. They do not invent metric deltas or rollback commits; contextual risks and test coverage are agent report responsibilities. |
| 25 | Finding evidence | Automated findings require semantic fields, their declared source check's captures, and valid artifact references. The guide labels source-inspection hypotheses. Validator cannot prove a claim's meaning. |
| 26 | Production attribution | Steps require one stated intent and exact bounded changes. Semantic line-to-objective attribution remains contextual agent review. |
| 27 | Fresh reviewer | Automated fresh manifest loading, independent artifact validation, real subprocess CLI, and `git apply --check` replay. Real-repository pilots are separate; arbitrary environment provisioning and a full benchmark evaluator are not bundled. |

## Agent workflow review

The workflow was read against three tabletop situations: a long linear
function with no demonstrated maintenance cost; an authorization test that
mocks away the permission boundary; and a repair with a known failing
regression baseline. The guide directs contextual no-edit judgment, a boundary
oracle that actually exercises permissions, and the direct authorized repair
workflow with the red baseline retained. Runner repair remains narrower: it
executes supplied behavior-preserving changes only after a green baseline.

This is an instruction review, not a blinded model trial. The guide does not
automatically classify styles, discover invented integrations, judge test
independence, infer authorization intent, or prove semantic equivalence.

## Remaining empirical work

The blueprint's paired baseline-agent versus anti-slop-agent experiment has not
been performed. There is no measured claim about reduced review time, hidden
regression rates, false-positive rates, median diff size, general mutation
scores, long-term maintainability, or cross-model performance. Confidence
intervals and corpus-calibrated quality thresholds remain study outputs.

Automated characterization generation, semantic codemods, hotspot analysis,
integration-specific security scanners, property-test generation, and a full
27-case cross-repository agent benchmark are not implied by local fixture
acceptance. The skill explains how to select these tools where a task needs
them. Real repository pilot results are recorded separately in
`research/pilot-results.md` when produced.

## Run record

Final integrated execution on 2026-10-04 passed **81 tests, zero skips**, in
1.781 seconds outside the outer restriction that prevents Bubblewrap startup.
This includes the real host-file/network boundary checks, real CLI refactor
and failed-step repair smoke, and byte-accurate patch replay. Standard-library
compilation also passed during acceptance work.

The earlier restricted execution run found 80 tests: 76 passed and 4 real
Bubblewrap tests explicitly skipped because the outer restriction denied
`NETLINK_ROUTE`. That run alone did not establish the isolation claims; the
final zero-skip execution above did exercise those cases.
