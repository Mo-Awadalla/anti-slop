# Evidence and Judgment

Use this reference to turn a repository signal into a defensible finding and qualify verification claims. The preserved research provides rationale and examples, not evidence that a particular repository has a defect.

## From signal to finding

Each finding needs an observed signal, repository-specific context, predicted cost or risk, confidence, a counterargument or falsifier, and an action with a verification method. Cite the inspected location, contract, caller, history, or captured tool output supporting the observation. Label an unconfirmed mechanism as an agent hypothesis.

| Class | Evidence that earns a finding | Plausible counterargument |
| --- | --- | --- |
| Style | Explicit formatter, linter, or project convention; or a demonstrated review cost | The difference is local preference and preserves the convention that matters |
| Maintainability | Duplicated policy that can drift, a repeated change across unrelated modules, an unnecessary dependency boundary, or inability to isolate relevant behavior | The abstraction protects an actual integration, ownership, or compatibility boundary |
| Behavior/security | A reproducible incorrect result or an affected input, error, authorization, persistence, or resource path | Existing surrounding logic or a documented contract prevents the alleged failure |

Size, nesting, abstraction counts, coverage, churn, and static-analysis alerts are leads. Explain the consequence in the target's actual change paths before recommending edits. A small authorization change can deserve more scrutiny than a large mechanical change.

Prefer evidence at the behavior boundary. A test that derives its expected value through the implementation, mocks away the relevant permission check, or asserts only that a call completed provides weak support. For an added regression or characterization oracle, inspect the assertions and use a representative negative case or temporary mutation when needed to show it detects the defect.

Confidence expresses uncertainty in the claim; it is not a calculated quality score. Rank findings by explained impact and relevance, without multiplying arbitrary factors or selecting universal cutoffs.

## Baseline and comparison

A baseline records what was true before the change:

- repository revision, branch, relevant working changes, and reviewed scope;
- applicable instructions and selected exact checks;
- results, exit codes, useful output, and execution limitations;
- observable behavior and important boundary cases covered by the checks.

Compare the final state with that baseline. A repair needs evidence that the target failure is resolved and relevant previously passing behavior remains intact. A refactor needs evidence for the declared invariant, including public and side-effect boundaries it touches. Passing checks alone do not prove semantic equivalence.

Keep pre-existing failures visible. A pass/fail or fail/pass rerun is flaky. Failed, unavailable, skipped, and unrun checks remain distinct from passing checks. Resolve an unexplained baseline failure before relying on that check as the comparison oracle; independently verified work may continue.

Verify an intentional behavior change against the requested new contract and report it. Updating an expectation merely to match generated output does not establish authorization or correctness.

## Runner evidence

The runner records Git discovery, exact checks, attempts, stdout/stderr, duration, and artifact references. Write runs also record supplied change steps and their verification and recovery outcome. Read the [operating contract](operating-contract.md) for current JSON and execution constraints.

For supplied JSON findings:

- `path`, `line`, and `column` locate the issue;
- `source` identifies a recorded check; `evidence_refs` name its captured artifacts;
- `impact`, `confidence`, and `counterargument` explain the claim and its limits;
- `recommended_action` includes concrete remediation or verification;
- `severity` communicates consequence; the title can name the risk class.

The validator checks source and artifact references, duplicates, required fields, and basic actionable structure. It cannot establish contextual correctness. Keep source-inspection hypotheses in the agent report unless their evidence is represented by the runner contract.

Artifact hashes and sizes detect missing or changed evidence at validation time. They are not tamper-proof storage against the same operating-system user. A run's `passed` status describes recorded checks and execution gates, not a universal clean-code verdict or proof of full behavior preservation.

## No-edit and completion claims

“No supported improvement found in the reviewed scope” is a valid diagnosis, including when cleanup lacks benefit. List verification gaps alongside it.

A clean verified result requires all required checks to pass with valid evidence and no unresolved actionable findings in scope. Runner results additionally require source immutability and valid sandboxed execution. Empty findings, an asserted status, or a lower metric cannot substitute for evidence.

For an incomplete or recovered edit, report the retained change, failed step and evidence, and restored checkpoint. A recovered failure is not a completed repair.

## Research traceability and limits

The source documents remain unchanged under `research/`. These pointers locate the rationale:

| Operational decision | Preserved source |
| --- | --- |
| Judge context, logic, behavior, and ownership rather than AI provenance | [Practitioner interpretation](../research/slop_practitioner_research.md#confidence-and-interpretation), including GitHub maintainer counterexamples |
| Investigate review burden, invented integrations, weak tests, and hidden authorization paths | [Practitioner taxonomy](../research/slop_practitioner_research.md#candidate-evidence-based-taxonomy-for-downstream-design), with underlying examples and limitations |
| Make small behavior-preserving steps with recovery and boundary verification | [Blueprint principles](../research/anti-slop-coding-agent-blueprint.md#2-source-grounded-design-principles) and [workflow](../research/anti-slop-coding-agent-blueprint.md#4-required-workflow) |
| Characterize unknown behavior and test oracle sensitivity | [Blueprint acceptance cases](../research/anti-slop-coding-agent-blueprint.md#7-acceptance-test-suite), characterization, weak-test, mutation, and contract cases |
| Use contextual metrics and evaluate clean controls as well as defects | [Blueprint evaluation design](../research/anti-slop-coding-agent-blueprint.md#8-evaluation-metrics-and-experiment-design) |

Practitioner sources include self-selected discussions, anecdotal reports, qualitative coding, and vendor-affiliated commentary. They support investigation of recurring mechanisms, not prevalence, universal defect multipliers, or causality.

The blueprint proposes scores, default diff thresholds, architecture, and review gates. These proposals are not current implementation requirements. This workflow uses user scope, explicit contracts, justified bounds, and available evidence. Security or public-interface work needs checks appropriate to its consequences; existing task authorization determines whether additional human input is necessary.

The [research index](../research/README.md) records missing reports. Preserve that gap. The [qualitative forward evaluation](../research/skill-evaluation.md) records local agent decisions and their limits. Fixture acceptance and pilot runs can validate local behavior; claims that the skill improves agent outcomes require the paired evaluation described in the blueprint, which is a separate empirical claim.
