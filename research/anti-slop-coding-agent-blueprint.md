# Anti-Slop Coding-Agent Skill/Plugin — Implementation Blueprint

**Status:** design requirements
**Audience:** authors of a language/repository-agnostic coding-agent skill or plugin
**Primary goal:** help an agent reduce accidental complexity and repair slopified code while preserving observable behavior, with evidence, bounded diffs, and reversible steps.

## 1. Problem definition and non-goals

“Slop” is not a formatting preference. For this skill, it means code or workflow choices that increase the cost or risk of understanding, testing, changing, or operating software without a demonstrated user or system benefit. Examples include speculative abstractions, duplicated branching, wrapper/delegation layers with no boundary value, broad rewrites, unverified generated tests, dead code, accidental API changes, and dependency/config churn.

The skill must distinguish:

| Category | Default treatment | Evidence required |
|---|---|---|
| **Style preference**: naming taste, line length, brace/quote convention, local formatting | Do not block a behavior-preserving change unless repository policy requires it | Existing formatter/linter config or explicit project rule |
| **Maintainability risk**: high nesting/branching, duplicated policy logic, excessive coupling, unclear ownership, dead paths, giant diffs, speculative generality | Investigate and prioritize when it affects a changed or high-risk area | Static metric, history/hotspot evidence, review finding, or concrete change/test cost |
| **Behavior/security risk**: changed API contract, permission checks, data handling, error semantics, concurrency, migration, dependency supply chain | Hard gate; require targeted verification and appropriate review | Tests/contracts/scans/manual review/rollback plan |

The agent must not “clean” a whole repository merely because a tool reports findings. It should fix the smallest high-impact slice supported by evidence.

**Non-goals:** automatic aesthetic normalization, universal complexity thresholds, replacing human review for security/concurrency/product decisions, inferring intended behavior from the current implementation alone, or claiming equivalence from passing tests only.

## 2. Source-grounded design principles

1. **Behavior-preserving, incremental refactoring.** Fowler defines refactoring as changing internal structure without changing external behavior and emphasizes small transformations that keep the system working. Refactoring.guru likewise recommends stepwise changes with tests after each change. The skill therefore uses short inspect → change → verify loops, not a rewrite-first strategy.
   - Sources: [Fowler refactoring](https://martinfowler.com/tags/refactoring.html), [Refactoring.guru process](https://refactoring.guru/refactoring).

2. **Reviewability is a safety property.** Google’s review guidance asks whether code is more complex than necessary, whether tests can fail for real defects, and warns against mixing major style changes with functional changes. GitHub documents that small, focused pull requests are easier to review and safer to merge. Linux patch guidance says one logical change per patch and “solve only one problem per patch.”
   - Sources: [Google code review checklist](https://google.github.io/eng-practices/review/reviewer/looking-for.html), [GitHub focused PRs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/getting-started/helping-others-review-your-changes), [Linux patch submission](https://www.kernel.org/doc/html/latest/process/submitting-patches.html).

3. **Current behavior must be captured before changing unknown code.** Characterization/approval tests record what the system actually does; they are a safety net, not proof that behavior is desirable. Prefer focused assertions where intent is known; use snapshots/golden masters for complex outputs, then review and normalize volatile fields.
   - Sources: [Michael Feathers on characterization testing](https://michaelfeathers.silvrback.com/characterization-testing), [Approval Tests](https://approvaltests.com), [Gilded Rose refactoring kata](https://github.com/emilybache/GildedRose-Refactoring-Kata).

4. **Tests must test behavior, not merely execute lines.** Mutation testing makes small production changes and checks whether the test suite detects them; this is stronger evidence than line coverage alone. Property-based testing checks invariants across generated edge cases. Contract testing protects integration boundaries without requiring every system to be deployed together.
   - Sources: [Cosmic Ray](https://cosmic-ray.readthedocs.io/en/latest/), [Hypothesis](https://hypothesis.readthedocs.io/en/latest/), [Pact](https://docs.pact.io).

5. **Use tools as signals, not verdicts.** Linters/formatters enforce repository conventions and catch local defects. Semgrep can encode project-specific patterns and invariants, including review comments and safe exemptions. CodeQL finds security variants. CodeScene demonstrates prioritizing poor code health in change hotspots rather than treating every finding equally.
   - Sources: [pre-commit](https://pre-commit.com), [Semgrep rule ideas](https://docs.semgrep.dev/writing-rules/rule-ideas), [CodeQL](https://codeql.github.com/docs/codeql-overview/about-codeql), [CodeScene hotspots](https://codescene.io/docs/guides/technical/hotspots.html).

6. **Small batches improve recovery and measurement.** DORA explicitly recommends reducing batch size because smaller changes are easier to rationalize and recover from. Git’s `bisect` can locate the first bad commit when intermediate states are testable. The skill must create checkpoints before risky work and retain a rollback path.
   - Sources: [DORA metrics](https://dora.dev/guides/dora-metrics), [git-bisect](https://git-scm.com/docs/git-bisect).

7. **AI output is untrusted until understood and verified.** GitHub’s Copilot guidance says to understand and carefully review generated code, considering functionality, security, readability, and maintainability, and to use tests, linting, code scanning, and IP scanning. NIST SP 800-218A extends secure-development practices for AI-related development across the lifecycle.
   - Sources: [GitHub Copilot best practices](https://docs.github.com/en/copilot/get-started/best-practices), [NIST SP 800-218A](https://www.nist.gov/news-events/news/2024/07/secure-software-development-practices-generative-ai-and-dual-use-foundation).

## 3. Skill contract and operating modes

The skill should expose three modes:

- `diagnose`: read-only inventory and ranked findings; no edits.
- `refactor`: bounded, behavior-preserving work on an approved target and objective.
- `repair-slop`: staged cleanup of an existing area, starting with a baseline and characterization tests; may stop after diagnosis if safety evidence is insufficient.

Inputs:

```yaml
mode: diagnose | refactor | repair-slop
scope: paths, symbols, or issue
objective: concrete maintainability or bug goal
behavior_budget: preserve | intentional-change (requires explicit contract)
max_files: integer or repository default
max_changed_lines: integer or repository default
max_steps: integer
risk_class: normal | high   # auth, payments, data deletion, migrations, concurrency, secrets, public API
```

Outputs must include a machine-readable run manifest and a human-readable report:

```yaml
run_id: ...
base_commit: ...
scope: ...
objective: ...
mode: ...
commands:
  - command: ...
    exit_code: 0
    output_artifact: ...
baseline:
  tests: pass|fail|not-found|not-run
  lint: ...
  typecheck: ...
  build: ...
  security: ...
  metrics: ...
changes:
  - step: 1
    intent: ...
    files: []
    additions: 0
    deletions: 0
    verification: []
    rollback: git revert <commit>
status: passed | stopped | blocked | rolled_back
unverified: []
```

Never report a check as passed if it was skipped, flaky, unavailable, or only inferred from another check.

## 4. Required workflow

### Phase A — Establish the baseline

1. Confirm repository root, current branch/commit, dirty working tree, package/build metadata, CI configuration, local agent instructions, and generated/vendor directories.
2. Identify the project’s canonical commands from documentation and CI; do not invent a replacement command before trying the project’s own command.
3. Run the smallest relevant baseline checks, then expand for high-risk changes: focused tests, full tests, build/typecheck, formatter/linter, security/dependency scan, and API/schema/contract checks.
4. Record failures separately from newly introduced failures. A pre-existing red baseline is not permission to ignore new regressions.
5. Capture a scope map: entry points, callers, public interfaces, side effects, persistence, network/queue boundaries, feature flags, error behavior, concurrency, and tests.
6. Collect signals: complexity/size, duplication, dependency/call graph, churn and change coupling where history is available, and hotspot activity. Prefer changed/high-risk hotspots over global issue counts.

Baseline diagnosis must terminate with one of:

- `safe-to-refactor`: observable behavior has adequate coverage and checks are green;
- `characterize-first`: behavior is reachable but insufficiently specified;
- `repair-baseline-first`: baseline failure prevents safe comparison;
- `human-review-required`: security, concurrency, public contract, migration, or ambiguous intent exceeds the agent’s authority.

### Phase B — Define the smallest useful change

Produce a plan before editing:

- one problem statement, one target, one behavior invariant;
- files/symbols in scope and explicit out-of-scope list;
- proposed sequence of atomic transformations;
- tests/characterization/contract cases to add or update;
- expected metric movement, if any;
- risk and rollback point.

The agent must reject or split plans that mix formatting-only changes with behavior changes, combine unrelated smells, add speculative extension points, or require a large rewrite to prove a local objective.

### Phase C — Add safety net

Choose the narrowest adequate test layer:

1. Existing tests and public API/contract tests.
2. A focused regression test for the requested defect.
3. Characterization tests around observed behavior when intent is unknown.
4. Golden master/approval tests for complex serialized outputs, with deterministic normalization of timestamps, IDs, ordering, and environment data.
5. Property-based tests for invariants such as round trips, idempotency, conservation, ordering, and boundary behavior.
6. Consumer/provider contract tests for integration boundaries.

A generated test is evidence only after the agent demonstrates that it can fail for a deliberately injected defect or killed mutant and that assertions are independent of the implementation under test. Never change a test merely to make a refactor green unless the behavior contract changed and the change is explicitly recorded.

### Phase D — Execute staged refactoring

Default sequence:

1. **Preparation:** introduce a seam, name, adapter, characterization fixture, or dependency boundary without changing behavior.
2. **One structural move:** extract/move/rename/replace one construct, or remove one demonstrably dead path.
3. **Verify immediately:** run the narrowest relevant test plus syntax/type/build checks.
4. **Checkpoint:** save a small commit or patch with one-line intent and evidence.
5. **Repeat:** only if the previous step is green and the diff remains within budget.
6. **Consolidate only after verification:** optional cleanup of temporary seams, still as a separately reviewable step.

Prefer AST/semantic codemods or repository-supported refactoring tools for mechanical transformations. OpenRewrite is a concrete example: recipes operate on semantic lossless syntax trees and aim for minimally invasive edits that preserve formatting. For unsupported or semantically ambiguous transformations, use a small manual patch and inspect every changed line.

### Phase E — Diff control and review

The plugin must calculate:

- files changed, added/deleted lines, changed hunks;
- formatting-only line ratio;
- production/test/config/dependency split;
- public API/schema/permission/migration touch points;
- churn outside declared scope;
- diff entropy: number of unrelated directories, symbols, or change categories.

Defaults should be configurable, not universal. Suggested initial guardrails:

- warn at > 5 files or > 150 changed lines for a refactor step;
- block at > 10 files or > 300 changed lines unless the plan explicitly justifies it;
- block any unexplained dependency/config/lockfile change;
- block formatting-only churn mixed with functional edits;
- require a split when a commit has more than one independently describable objective.

A threshold is a tripwire, not a quality score. A 20-line auth change can be higher risk than a 500-line generated migration.

### Phase F — Verification and rollback

Verification order:

1. changed tests and characterization/approval outputs;
2. affected package/module tests;
3. integration/contract tests for touched boundaries;
4. full test suite, build, typecheck, lint/format check;
5. security, dependency, secret, and policy scans for relevant changes;
6. behavior comparison against the base revision for representative inputs where feasible;
7. human review of the final diff, including unchanged surrounding context and generated files.

On failure:

- classify baseline failure, agent regression, flaky/environment failure, or intentional contract change;
- stop editing if the cause is unclear;
- return to the last green checkpoint or `git revert` the step;
- use `git bisect` only across testable checkpoints;
- report the exact failed command and artifact.

Never “fix” a failing test by weakening assertions, deleting coverage, widening mocks, suppressing a linter without rationale, or changing unrelated code.

### Phase G — Stopping rules

Stop with `blocked` or `human-review-required` when:

- baseline is not understood;
- required behavior has no adequate oracle and characterization is unsafe or nondeterministic;
- a step exceeds the diff/risk budget;
- tests are flaky or cannot be run reproducibly;
- public behavior, permissions, concurrency, migrations, secrets, billing, deletion, or dependency provenance changes;
- the agent cannot explain a changed line or its invariant;
- a tool proposes a cosmetic fix with no maintainability or correctness case;
- metric improvement requires a more complex abstraction than the original;
- repeated repair attempts (default: two) do not converge;
- the remaining work is lower-value than the risk or would require a rewrite.

A successful stop can be “no edit made; diagnosis and next safe step delivered.”

## 5. Diagnosis rubric: style versus slop risk

Each finding should have `evidence`, `impact`, `confidence`, `recommended_action`, and `counterargument`.

Prioritize using a transparent score, for example:

`priority = impact × confidence × change_frequency × risk_reduction`

Do not treat this as a universal formula. Each factor must be explainable.

High-value signals:

- a complex area that is frequently changed or defect-prone;
- duplicated business rules that drift;
- code that lacks tests at a public boundary;
- hidden side effects, unclear error/transaction semantics, or broad coupling;
- generated/AI code with unreviewed dependencies or privilege boundaries;
- a failing mutation/property/contract test exposing a weak oracle.

Low-value signals by themselves:

- formatter disagreement with an untouched legacy file;
- a single long function with simple linear logic;
- a naming preference not used by repository policy;
- low coverage in generated/vendor code;
- a static-analysis warning in stable code never likely to change.

## 6. Proposed skill/plugin architecture

```text
anti-slop/
├── SKILL.md                    # trigger, workflow, safety contract
├── references/
│   ├── evidence-map.md         # source-backed rationale and limits
│   ├── risk-rubric.md          # style vs maintainability vs behavior risk
│   └── report-schema.yaml
├── scripts/
│   ├── detect-repo.py          # discover language, build/test/lint commands
│   ├── baseline.py             # run and capture checks
│   ├── diff_budget.py          # scope, hunk, churn, API/config checks
│   ├── characterize.py         # adapter for snapshots/approval/golden master
│   ├── verify.py               # staged verification and evidence manifest
│   └── score_metrics.py        # before/after metrics with caveats
├── adapters/
│   ├── generic-git.yaml
│   ├── python.yaml
│   ├── javascript.yaml
│   ├── jvm.yaml
│   └── dotnet.yaml
├── fixtures/
│   ├── slop-small-diff/
│   ├── legacy-untested/
│   ├── hidden-contract/
│   ├── flaky-baseline/
│   ├── security-sensitive/
│   └── clean-control/
└── tests/
    ├── acceptance/
    ├── mutation-seeds/
    └── golden-reports/
```

The core should be language-agnostic and delegate language-specific execution to adapters. Adapters declare commands and parsers; they must not silently fall back from a failed project command to a different tool. All writes happen inside an isolated branch/worktree or an explicit user-approved working tree.

## 7. Acceptance test suite

The plugin is acceptable only if it passes these behavioral tests against fixture repositories and at least two real open-source repositories in different languages.

### A. Baseline and evidence

1. **Clean baseline:** detects repository root, branch, commit, test/build/lint commands; produces a manifest with actual exit codes.
2. **Dirty tree:** refuses to overwrite unrelated changes; reports them and requests an isolated worktree or explicit scope.
3. **Pre-existing failure:** labels the baseline red and does not claim the refactor caused it.
4. **Unknown command:** reports `not-run` and `blocked`/`human-review-required`; never fabricates a pass.
5. **High-risk target:** auth/payment/migration/concurrency fixture requires targeted checks and human review.

### B. Characterization and testing

6. **Untested legacy module:** creates a minimal characterization harness for stable observable output, records volatile-field normalization, then proves the fixture detects a behavior change.
7. **Golden-master approval:** a deliberate approved output change updates the fixture only with explicit contract-change metadata; an unapproved output change blocks.
8. **Weak generated test:** fixture test asserts the function’s own output as its expected value; plugin flags it as non-independent.
9. **Mutation gate:** inject a known operator/branch mutation; acceptance fails if the test suite does not kill it or explain the surviving mutant.
10. **Property invariant:** refactor preserves a supplied invariant across generated edge cases.
11. **Integration contract:** provider response change that breaks a consumer contract is caught before final status.

### C. Diff and staged execution

12. **Small atomic refactor:** performs one transformation, runs focused checks, records a checkpoint, and leaves a reviewable diff.
13. **Scope creep:** agent attempts an unrelated formatting pass or dependency update; plugin blocks or splits it.
14. **Budget breach:** a fixture requiring > configured files/lines emits a split recommendation and does not continue automatically.
15. **Rollback:** inject a failure after step two; plugin returns to the last green checkpoint and preserves the failure artifact.
16. **Bisectable sequence:** a regression introduced in step three is localized to that checkpoint by `git bisect` or equivalent evidence.
17. **Semantic codemod:** an approved mechanical transformation changes only matching syntax and preserves unrelated formatting/content.

### D. Maintainability outcomes

18. **Style-only control:** changing naming/formatting preference alone is reported as non-blocking unless repository policy says otherwise.
19. **Risky complexity:** fixture with nested branching and duplicated policy in a frequently changed hotspot is prioritized above a larger but stable low-risk file.
20. **Over-engineering trap:** proposed generic plugin/abstraction for one current case is rejected unless it reduces measured complexity or risk.
21. **No metric gaming:** agent cannot pass by deleting tests, suppressing findings, increasing thresholds, or replacing assertions with snapshots of the implementation.
22. **No negative tradeoff:** if complexity/LOC decreases but coupling, public API surface, test weakness, or risk increases, status is not passed.
23. **Clean control:** already-simple code is left unchanged with a concise “no safe/high-value improvement found” report.

### E. Reporting and trust

24. Every final report lists files changed, commands run, exit codes, tests added/changed, skipped checks, baseline failures, metric deltas, risks, and rollback commit.
25. Every finding links to a source/tool result or explicitly says it is an agent hypothesis.
26. Every changed production line is attributable to the approved objective or a documented prerequisite.
27. A fresh reviewer process can reproduce the verification from the manifest without relying on hidden agent context.

## 8. Evaluation metrics and experiment design

Evaluate the skill against a fixed corpus of slopified and clean repositories, with paired runs: baseline agent versus anti-slop agent, same model and task budget.

### Safety metrics

- functional pass rate: requested tests plus unrelated pass-to-pass tests;
- regression rate on hidden tests and contracts;
- characterization mismatch rate, with intentional changes separated;
- mutation score delta in touched code;
- security finding rate and escaped high-risk issue rate;
- rollback success rate and mean time to safe checkpoint;
- false claims: “passed” while skipped, flaky, or unavailable.

SWE-bench’s distinction between `FAIL_TO_PASS` and `PASS_TO_PASS` is a useful evaluation pattern: a fix must solve the target issue without breaking unrelated behavior. Source: [SWE-bench](https://github.com/swe-bench/SWE-bench), [SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified).

### Maintainability metrics

- changed-scope cyclomatic/cognitive complexity delta;
- duplication or repeated-policy count;
- dependency/coupling and public surface delta;
- test oracle strength: mutation score, independent assertions, contract coverage;
- diff size, unrelated-change ratio, and review time/defect detection;
- hotspot-weighted code-health improvement, not repository-wide score chasing;
- subsequent change cost: files touched, lead time, review iterations, and rollback/hotfix incidence.

Metrics are diagnostic and should be triangulated. Do not set a single universal “complexity below X” target. Record before/after values, tool versions, exclusions, and whether generated/vendor code was included.

### Quality bar

A release candidate should show, on the evaluation corpus:

- zero fabricated verification claims;
- no statistically or practically meaningful increase in hidden regression rate;
- reduced median diff size and unrelated-change ratio;
- improved mutation/contract evidence in touched areas;
- improved or neutral complexity/coupling in the target scope;
- successful rollback on injected failures;
- clean-control abstention rather than unnecessary edits.

Thresholds should be calibrated from the baseline corpus and reported with confidence intervals or paired per-task results. The skill should optimize for safe, comprehensible change—not for producing the largest numeric metric improvement.

## 9. Implementation order

1. **Manifest and safety shell:** repo discovery, dirty-tree protection, command execution, exit-code capture, report schema.
2. **Baseline adapter layer:** infer project commands from CI/docs; support generic Git plus two language adapters.
3. **Diff budget and scope gate:** changed-file/hunk/category analysis; split/stop behavior.
4. **Test evidence layer:** existing tests, characterization snapshots, deterministic normalization, independent-assertion checks.
5. **Staged checkpoint/rollback loop:** per-step verification and checkpoint metadata.
6. **Risk rubric and hotspot prioritization:** static metrics plus history when available; style/non-risk suppression.
7. **Security/integration gates:** CodeQL/Semgrep/dependency/secret/contract adapter hooks where configured.
8. **Evaluation fixtures and mutation seeds:** acceptance suite above, paired baseline comparisons.
9. **Optional language adapters and codemod integrations:** add only after the generic workflow is reliable.

The first production milestone is not “the agent cleans code.” It is: **the agent can inspect a repository, make one bounded behavior-preserving change, prove what it ran, stop safely when it cannot prove safety, and roll back cleanly.**

## References

- Martin Fowler, [Refactoring](https://martinfowler.com/tags/refactoring.html)
- Google Engineering Practices, [What to look for in a code review](https://google.github.io/eng-practices/review/reviewer/looking-for.html)
- GitHub Docs, [Helping others review your changes](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/getting-started/helping-others-review-your-changes)
- Linux Kernel, [Submitting patches](https://www.kernel.org/doc/html/latest/process/submitting-patches.html)
- DORA, [Software delivery performance metrics](https://dora.dev/guides/dora-metrics)
- Git, [`git bisect`](https://git-scm.com/docs/git-bisect)
- Michael Feathers, [Characterization testing](https://michaelfeathers.silvrback.com/characterization-testing)
- Approval Tests, [Approval testing](https://approvaltests.com)
- Emily Bache, [Gilded Rose Refactoring Kata](https://github.com/emilybache/GildedRose-Refactoring-Kata)
- Cosmic Ray, [Mutation testing for Python](https://cosmic-ray.readthedocs.io/en/latest/)
- Hypothesis, [Property-based testing](https://hypothesis.readthedocs.io/en/latest/)
- Pact, [Contract testing](https://docs.pact.io)
- pre-commit, [Framework documentation](https://pre-commit.com)
- Semgrep, [Rule ideas](https://docs.semgrep.dev/writing-rules/rule-ideas)
- CodeQL, [About CodeQL](https://codeql.github.com/docs/codeql-overview/about-codeql)
- CodeScene, [Technical debt and hotspots](https://codescene.io/docs/guides/technical/hotspots.html)
- OpenRewrite, [Automated refactoring documentation](https://docs.openrewrite.org)
- GitHub, [Best practices for using Copilot](https://docs.github.com/en/copilot/get-started/best-practices)
- NIST, [SP 800-218A announcement](https://www.nist.gov/news-events/news/2024/07/secure-software-development-practices-generative-ai-and-dual-use-foundation)
- SWE-bench, [Repository and evaluation](https://github.com/swe-bench/SWE-bench)
