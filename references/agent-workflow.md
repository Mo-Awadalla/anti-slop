# Agent Workflow

Use this guide for prevention, refactoring, or repair. Diagnosis follows the context and evidence decisions, ending before edits.

## Prevent during implementation

Follow the requested behavior through existing boundaries, error semantics, dependencies, and tests before adding a mechanism. Check additions against concrete need:

- An abstraction should protect a real boundary, remove repeated policy, or make the requested behavior easier to change or verify. A possible future consumer alone does not establish need.
- Verify that an integration, API, dependency, or option actually exists and serves the request, rather than filling a gap with a plausible name.
- Preserve error signals the caller depends on. Catching and logging can hide failure or bypass required work.
- Assert observable behavior independently, including relevant failures and boundaries. Keep the permission, transaction, or integration behavior being verified on the exercised path.

Inspect the diff for unexplained helpers, repeated rules, new public surface, dependency/configuration changes, and unrelated formatting. Retain additions that earn their cost and remove additions introduced only by generation. Stay within the requested task.

## Define the change

Identify the maintenance cost removed or failure fixed and the behavior kept stable. Refactors preserve observable behavior. Repairs distinguish the intended correction from unaffected behavior.

Identify affected paths and callers, allowed file categories, boundary cases, and a recovery point. Use project instructions and the existing request to determine authority. A request to fix or refactor an area authorizes necessary bounded work there, not unrelated product, dependency, or deployment changes.

Choose file, line, and step bounds from the task's review needs rather than fixed numbers. Sequence a large justified mechanical transformation into reviewable steps. Split a diff with independently useful objectives.

The plan is ready when every proposed production change serves the objective or an identified prerequisite, the contract is explicit, and a relevant oracle and recovery point exist. Clarify missing product intent; resolve routine implementation choices from context.

## Establish the oracle

Record relevant existing checks before changing code, including pre-existing failures. Choose the narrowest adequate test layer:

| Situation | Useful oracle |
| --- | --- |
| Known defect | A regression case failing on the defect and passing on the correction, plus relevant previously passing cases |
| Known public behavior | Focused API, error, and side-effect assertions |
| Unknown legacy behavior | Characterization of representative output, identifying what remains unknown |
| Complex serialized output | Reviewed golden output with deterministic normalization of volatile fields |
| Input invariant | Boundary or property checks for specified round trips, ordering, idempotency, or conservation |
| Integration boundary | Existing contract checks retaining the affected dependency behavior |

Characterization records current behavior, not desirable behavior. Normalize timestamps, identifiers, or ordering only when the normalization preserves the tested contract; record what it ignores.

Inspect new oracles for independence from the implementation. When an oracle justifies a risky preservation claim, demonstrate sensitivity through a representative failing case or temporary mutation in a disposable fixture. Resolve or report a surviving mutation or untested boundary.

Security, concurrency, migrations, destructive operations, and public contracts need checks targeted to their actual consequences. Additional review or input is needed when behavior intent or execution authority is missing; the category alone creates no blanket approval gate.

## Execute and recover

Preserve the original revision and relevant working changes. An isolated worktree, task-owned patch or commit, or runner snapshot can provide a recovery point. Avoid including unrelated user changes in a checkpoint.

Apply one logical transformation, inspect callers and changed lines, and run focused checks. Project-supported semantic tools can reduce ambiguity for mechanical changes; inspect their output. Use a manual patch for small or contextual transformations.

After a passing step, record intent, changed paths, and verification and proceed to the next justified step. Remove temporary seams when they no longer support the final design, within the objective.

On failure, retain command/output and compare with baseline. Distinguish regression, existing failure, environment failure, flakiness, and intentional contract change. Recover only the failed task step to the last verified checkpoint if it introduced a regression. In shared checkouts, preserve user and other-agent changes; a destructive whole-tree reset is not appropriate recovery.

Stop dependent edits while unexplained failure, inadequate oracle, exceeded scope, or missing behavior intent prevents trustworthy comparison. Resolve with a smaller supported step or report the specific missing evidence or intent. A fixed retry count does not substitute for learning from failure.

## Optional runner

The runner automates a narrower path: checks and supplied change steps on a disposable snapshot of a clean revision. It verifies a green baseline, checks each step, enforces declared bounds, and recovers failure. Verified completion exports a reviewable patch. It leaves the source checkout unchanged. Use the [operating contract](operating-contract.md) and current CLI help for exact input and output details.

The agent decides which code has an unjustified cost, prepares the steps, reviews assertions, and assesses behavior preservation. The runner does not generate changes or apply its patch to the source.

Both runner write modes require the selected baseline checks to pass. Therefore, a repair with a regression test that intentionally fails on the base may need the direct agent workflow: record that failure, prove the correction, and retain relevant passing checks. Do not conceal a red baseline or remove the regression oracle merely to qualify for a runner pass. Runner `repair-slop` executes supplied behavior-preserving changes under `behavior_budget: preserve`; intentional contract changes belong to the authorized direct agent workflow.

A missing sandbox or inadequate runner baseline remains a reported limitation. Ordinary authorized tools may still support direct agent work with its actual limits; that result is not a runner pass.

## Review and finish

Compare the final diff and surrounding code with the objective. Review tests for weakened assertions, expanded mocks, skipped cases, suppression, and justified expectation changes. Account for public surface, dependencies, configuration, generated files, and unrelated churn.

Run affected checks; expand to package, integration, build, type, lint, or security checks when the changed boundary warrants it. Repeat a completed check when subsequent changes invalidate it or an unresolved concern needs investigation.

Finish when requested objectives are complete, each changed line has a reason, relevant checks establish the claimed outcome, and limitations are explicit. Report the retained change and evidence; distinguish a stopped or recovered edit from a completed repair. A supported no-edit decision is useful when cleanup earns no benefit or cannot be justified safely.
