# Runner Operating Contract

The agent workflow in `SKILL.md` supports contextual prevention, diagnosis, refactoring, and repair. The optional standard-library Python runner implements a narrower deterministic contract. It requires Linux, Git, and operational Bubblewrap; the agent guidance is portable.

## Commands and outcomes

```bash
python3 scripts/run.py diagnose --spec run.json
python3 scripts/run.py refactor --spec run.json
python3 scripts/run.py repair-slop --spec run.json
python3 scripts/run.py validate-findings --manifest manifest.json --findings findings.json
```

The command and spec mode must match. A run prints JSON containing its status, manifest path, and report path. Exit `0` means the run's required checks and execution gates passed; `1` means a recorded failed, stopped, blocked, or flaky run; `2` means invalid input or a setup/validation error. Finding validation exits `0` for structurally valid findings, even when the associated checks failed; it does not certify their meaning.

Artifacts are stored in `$HERMES_HOME/cache/anti-slop/runs/<run_id>` (default `~/.hermes`). Set `HERMES_HOME` to a writable task directory when using a restricted workspace. Artifact destinations must be outside the source repository and snapshot. Run directories and snapshot destinations are exclusive; an existing destination is never overwritten. A run leaves its disposable snapshot available for review. Checkpoint copies are temporary and removed when closed.

## Diagnosis specification

See [run-spec.schema.json](../templates/run-spec.schema.json). Required fields are absolute `repo_path`, absolute `snapshot_root`, `mode`, and `checks`. Snapshot destinations must be outside the source repository and not already exist.

Each check names a unique `id`, a nonempty tokenized `argv`, and optionally `cwd`, `required`, `rerun`, or `timeout_seconds`. `cwd` defaults to the snapshot root; an absolute cwd must be inside it and is translated to `/workspace` inside the sandbox. The default timeout is 300 seconds when omitted or null. `rerun: true` records two attempts, classifying inconsistent results as flaky. `shell` is false; shell launchers and shell syntax in argv are rejected. Commands discovered in repository text are suggestions only.

Diagnosis discovers a clean Git revision, fingerprints its contents, file modes, HEAD, branch, and working state, then copies a disposable filesystem snapshot without `.git` metadata. It runs only supplied checks and verifies that the source identity remains unchanged. Dirty sources stop before execution. Symlinks are refused. No checks, or no required checks, cannot establish a pass. Unsupported ecosystems use generic supplied checks, without invented language-specific findings.

## Supplied change specifications

Both `refactor` and runner `repair-slop` currently preserve behavior. They require the diagnosis fields plus:

| Field | Meaning |
| --- | --- |
| `objective` | Concrete reason for the change |
| `behavior_budget` | Exactly `preserve` |
| `allowed_paths` | Exact relative files that may change; no globs |
| `oracle_checks` | Existing explicitly required check IDs supporting the invariant |
| `oracle_paths` | Existing nonempty files containing immutable assertions/contracts and their relevant helpers |
| `protected_paths` | Optional additional immutable files |
| `limits` | Positive `max_files`, `max_changed_lines`, `max_steps`, chosen for this task |
| `steps` | Finite ordered supplied changes; an empty list permits a verified no-edit result |

Each step has a unique `id`, a `description`, and nonempty `changes`. Each change contains `path`, `before_sha256`, and `content`. Supply the SHA-256 of current bytes when modifying or deleting; use null when creating. `content` is the complete replacement UTF-8 text, or null to delete an existing file. Null hash plus null content is invalid. A stale hash blocks the step before mutation.

Change paths are relative POSIX file paths without whitespace or traversal. Only regular UTF-8 text changes are supported. Binary changes, symlinks, permission changes, Git metadata, CI/agent configuration, dependency manifests, and protected configuration surfaces are refused. The guard implementation in `diff_budget.py` defines those categories. Declare the complete oracle/helper boundary: detecting assertions independent of the production implementation remains an agent review responsibility. Files directly named by check argv are additionally protected when identifiable.

Every supplied check is required and run twice at baseline and after each step, including checks originally marked optional. Both modes require every baseline check to pass before edits. A failing baseline remains visible; no steps are applied. This runner does not implement intentional behavior changes or a red-to-green bug-fix contract. Use the authorized direct agent repair workflow for those tasks, with independent regression and preservation evidence.

For each step, the runner captures a checkpoint, applies only the supplied contents, checks scope and per-step/net/cumulative diff budgets, runs the complete check set, and rejects checks that modify the snapshot. Added plus deleted lines count as changed lines; repeated churn also spends the cumulative budget. A failed step is restored to the previous verified tree and the run stops, retaining failed attempts and audit evidence. Earlier verified changes remain in the snapshot; a stopped run exports no final patch.

Completed runs verify source immutability and export `write/final.patch` plus `write/evidence.json`. The audit records objective, declared oracles/bounds, baseline and per-step results, tree hashes, changed files and line counts, rollback, no-edit, and completion. The report links captures and records exact commands, exit codes, and uncertainty. A verifier checks artifact hashes/sizes, phase/check linkage, checkpoint chain, and final patch paths. `passed` describes the supplied gates, not proof of all behavior or maintenance benefit. The same operating-system user can rewrite evidence and hashes; this is integrity checking, not signed attestation.

The runner never applies the final patch to the source checkout, generates edits, executes arbitrary codemods, or creates source commits. Review the patch and its base revision before applying it within an authorized task. Preserve unrelated working changes.

## Isolation and evidence

Checks execute through Bubblewrap with no network, separate PID/IPC/UTS namespaces, cleared environment, dropped capabilities, read-only system runtimes/certificates, disposable temporary/home directories, and only the snapshot writable. Source files, host home, Git metadata, and arbitrary host directories are not mounted. A missing executable, unavailable sandbox, timeout, failed check, skipped check, or flaky rerun remains visible. There is no unsandboxed fallback.

Every attempt has stdout/stderr captures with SHA-256 and byte count. Verification rejects missing metadata, changed artifacts, symlink aliases, inconsistent references, and unsandboxed pass attempts. Finding sources must name recorded checks and reference captures from that same check. The [finding schema](../templates/findings.schema.json) requires impact, confidence, action, and counterargument; legacy input cannot fabricate them. Contextual findings from inspection belong in the agent report unless represented by captured checks.

## Verification

From `scripts/`:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q run.py anti_slop_core tests
python3 run.py --help
```

The suite includes deterministic fixture tests and actual CLI/Bubblewrap tests. Real isolation tests capability-probe and explicitly skip when the host cannot start Bubblewrap; skips are not sandbox verification. See [acceptance results](../research/acceptance-results.md), [pilot](../research/pilot-results.md), and [skill evaluation](../research/skill-evaluation.md) for recorded evidence and limits. Keep implementation standard-library-only and preserve source research.
