# Skill forward evaluation

Recorded on 2026-10-04 in the user's America/New_York date context. The skill author agent followed the finished `SKILL.md`, agent workflow, and evidence baseline on five synthetic local requests. Expected decisions were known to that agent. This is a single-agent qualitative forward evaluation with executed fixture checks, not a blinded model trial, paired corpus study, or measured improvement over an agent without the skill.

## Requests, decisions, and observed evidence

| Request and raw fixture | Expected decision | Actual agent decision and local result |
| --- | --- | --- |
| Diagnose a linear customer serializer with fixed field order, required-field errors, and no contrary style rule | Investigate context; leave code unchanged if size or personal style is the only signal | Reviewed the ordered output contract and independent expected string. Found no demonstrated maintenance cost. Both existing tests passed, exit 0; before/after production SHA-256 matched and the diff was empty. Qualified no-edit to this function and its exercised contract. |
| Add one optional receipt discount, default 0, range 0–1; a generic strategy/factory registry is proposed without a second use | Implement the requested behavior in the existing boundary; omit speculative machinery | Extended the existing pure function with the parameter and range check. Changed only the function and its focused tests; introduced no registry, dependency, or configuration. Existing two tests passed before; all six tests passed afterward, exit 0, covering old callers, empty input, discount, full discount, and invalid bounds. |
| Fix a permission bug: only an authenticated owner may read; the request already authorizes edits and two regression cases fail | Preserve the red baseline record and repair the intended behavior directly; avoid a redundant approval gate or runner pass claim | Recorded two failures and two passes, exit 1. Replaced the erroneous `or` with `and` in the permission predicate; retained tests and unrelated title behavior. Four tests passed afterward, exit 0. Used the authorized direct workflow because runner writes require a green preservation baseline. |
| Assess a generated test `assertEqual(multiply(2, 3), multiply(2, 3))`; product code adds an erroneous 1 | Reject the tautology as an oracle; use independent expected outputs and show sensitivity | The original test passed, exit 0, despite incorrect output. Replaced it with explicit positive, zero, negative, and fractional products: all four failed on the original defect, exit 1. Removed the erroneous addition: all four passed, exit 0. Temporarily restored `+ 1`: four failures, exit 1; restored the correction and observed four passes, exit 0. |
| Diagnose a clean Git fixture when required Bubblewrap is unavailable | Report unavailable checks; preserve the source and avoid host fallback or a clean claim | Injected only missing `bwrap` discovery into the production diagnosis path. The manifest derived `blocked`, with the check `unavailable`. Neither source nor snapshot check marker was created; source fingerprint matched. The report said no-edit correctness was not established. This injection verifies missing-tool handling, not sandbox isolation. |

The fixtures and command captures are retained in [skill-evaluation-evidence/](skill-evaluation-evidence/results.json). Each Python fixture check used `python3 -B -m unittest -v test_module` in its scenario directory. `results.json`, before-images, final diffs, and stage captures retain the local outcomes. The unavailable scenario also retains the production manifest and report under its isolated artifact directory. These are saved evaluation artifacts, separate from the preserved source research and the runner's real sandbox acceptance evidence.

## Matt's skill-writing criteria

The author read Matt Pocock's `writing-great-skills/SKILL.md` and `GLOSSARY.md` from the supplied backup, alongside the current skill-authoring instructions. The evaluation exercised these decisions:

- **Branches and context pointers:** prevention, diagnosis, refactor, and repair are distinct entry cases; code-changing work loads the agent workflow, contextual claims load the evidence reference, and runner use loads the operating contract.
- **Completion criteria:** the clean control needs a contextual reason to edit; prevention accounts for changed lines; repair compares failures and previously passing behavior; a new oracle must support its claimed boundary; unavailable execution cannot count as a pass.
- **Progressive disclosure and co-location:** the entrypoint carries shared decisions; oracle selection and recovery stay together in the code-changing reference. Runner specification details remain in the operating contract.
- **Pruning:** obsolete P0-only restrictions, prescribed universal thresholds, a quality score, and blanket approval gates were removed. Existing user scope and authorization remain authoritative.

The five cases exposed no new instruction ambiguity. They did reveal a concrete metadata routing issue, corrected below. A separate acceptance agent also reviewed three of these classes as tabletop instruction review; that is additional qualitative review, not independent empirical validation.

## Metadata and interface compatibility

The installed Hermes helper at `agent/skill_utils.py` in the installed Hermes runtime (line 761) limits the prompt description to 60 characters. The initial revised description exceeded this limit and lost later triggers through truncation. The final description is exactly 60 characters: `Prevent code slop; diagnose, refactor, repair with evidence.` The installed helper's extracted description functions returned the full text and `truncated: false` on the final YAML.

Codex's bundled skill validator accepts `name`, `description`, `license`, and `metadata`, and rejected the former top-level `author`, `version`, and `platforms` extensions. Author and version are retained under metadata. Hermes reads its OS gate from top-level `platforms`, so relocating that field would not preserve its former Linux-only discovery behavior. The final metadata instead declares `runner_platforms: [linux]`, and the body identifies the portable agent workflow and optional Linux runner. The installed helper's extracted platform function admitted Linux, macOS, and Windows; this is deliberate discovery portability, not a claim that the runner works on those operating systems. No cross-platform execution was performed.

`metadata.hermes.tags` and `related_skills` remain in the location consumed by the inspected Hermes loader. No explicit-only invocation flag was introduced. Metadata helper checks used the actual selected source functions without loading runtime configuration; the skill was not installed or activated in Hermes during this evaluation.

The current CLI exposes `diagnose`, `refactor`, `repair-slop`, and `validate-findings`. Both write modes accept supplied full-text change steps, enforce `behavior_budget: preserve`, protect declared existing oracle files, require passing baseline checks, recover failed snapshot steps, and export the final patch only after verified completion. The skill keeps those mechanics distinct from direct authorized repairs with an intentional contract correction or red regression baseline.

The bundled skill validator reports `Skill is valid!`; whitespace checks and local reference/anchor checks pass. These validate packaging and local compatibility details, not automatic trigger selection across arbitrary prompts.

## Limits

The qualitative outcomes support these particular decisions and fixture oracles. They provide no prevalence estimate, general false-positive rate, review-time reduction, hidden-regression rate, or cross-model effectiveness claim. Baseline-agent versus anti-slop-agent comparisons, unseen tasks, multiple languages and models, repeated trials, and the blueprint's full paired evaluation remain unperformed. Local acceptance tests and real repository pilots are reported separately.
