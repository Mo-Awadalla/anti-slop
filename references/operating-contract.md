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

Artifacts are stored in `$HERMES_HOME/cache/anti-slop/runs/<run_id>` (default `~/.hermes`). Set `HERMES_HOME` to a writable task directory when using a restricted workspace. Artifact destinations must be outside the source repository and snapshot. Run directories and snapshot destinations are exclusive; an existing destination is never overwritten. A run leaves its disposable snapshot available for review. Successful checkpoints are removed when closed; a failed restoration retains recovery staging and its path in write evidence.

## Diagnosis specification

See [run-spec.schema.json](../templates/run-spec.schema.json). Required fields are absolute `repo_path`, absolute `snapshot_root`, `mode`, and `checks`. Snapshot destinations must be outside the source repository and not already exist.

Each check names a unique `id`, a nonempty tokenized `argv`, and optionally `cwd`, `required`, `rerun`, or `timeout_seconds`. `cwd` defaults to the snapshot root; an absolute cwd must be inside it and is translated to `/workspace` inside the sandbox. The default timeout is 300 seconds when omitted or null. `rerun: true` records two attempts, classifying inconsistent results as flaky. `shell` is false; shell launchers and shell syntax in argv are rejected. Commands discovered in repository text are suggestions only.

Diagnosis discovers a clean Git revision and copies tracked regular files without `.git` metadata. Ignored and untracked content is excluded; tracked files remain included even when an ignore rule matches them. Keep secrets out of tracked source. The runner checks revision and working-state stability around the copy and fingerprints tracked bytes, modes, HEAD, and branch. Dirty sources stop before execution. Tracked symlinks and nonregular files are refused. Excluded local environments, ignored dependencies, or generated files must be supplied through a deliberate runtime environment rather than silently copied. No checks, or no required checks, cannot establish a pass.

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

Change paths are relative POSIX file paths without whitespace or traversal. Only regular UTF-8 text changes are supported. Binary changes, symlinks, permission changes, Git metadata, CI/agent configuration, dependency manifests, and protected configuration surfaces are refused. `diff_budget.py` defines those categories. Declare the complete oracle/helper boundary. The runner also follows static local Python imports from declared oracles and check scripts to protect assertion-bearing modules, conventional test/helper paths, and relevant package initializers. Independent production imports stay editable. Dynamic imports, custom helpers without those signals, and other languages still require explicit `oracle_paths` or `protected_paths`; automatic discovery does not prove assertion independence.

Check-file arguments under the sandbox's absolute `/workspace/` mount are protected through their corresponding snapshot paths. Check argv executes verbatim; use Linux executables available in the image and relative or mounted workspace arguments. The container launcher remaps cwd, not arbitrary argument strings.

Every supplied check is required and run twice at baseline and after each step, including checks originally marked optional. Both modes require every baseline check to pass before edits. A failing baseline remains visible; no steps are applied. This runner does not implement intentional behavior changes or a red-to-green bug-fix contract. Use the authorized direct agent repair workflow for those tasks, with independent regression and preservation evidence.

For each step, the runner captures a checkpoint, applies only the supplied contents, checks scope and per-step/net/cumulative diff budgets, runs the complete check set, and rejects checks that modify the snapshot. Added plus deleted lines count as changed lines; repeated churn also spends the cumulative budget. A failed step is restored to the previous verified tree and the run stops, retaining failed attempts and audit evidence. Earlier verified changes remain in the snapshot; a stopped run exports no final patch.

Completed runs verify source immutability and export `write/final.patch` plus `write/evidence.json`. The audit records objective, declared oracles/bounds, baseline and per-step results, tree hashes, changed files and line counts, rollback, no-edit, and completion. Write evidence includes replay inputs and final identities. Verification replays patch bodies against recorded baseline content and checks their resulting tree identities, rather than accepting path headers alone. The report records exact commands and uncertainty. `passed` describes supplied gates, not proof of all behavior or maintenance benefit. The same operating-system user can rewrite evidence and hashes; this is integrity checking, not authenticated attestation.

`write/evidence.json` uses `schema_version: 2`. Its `write/baseline-tree.json` contains the bytes and modes of every tracked baseline file, including unchanged files. Treat the evidence directory as sensitive repository content. The current validator rejects version-1 write evidence; preserved historical artifacts are not silently upgraded or recertified.

The runner never applies the final patch to the source checkout, generates edits, executes arbitrary codemods, or creates source commits. Review the patch and its base revision before applying it within an authorized task. Preserve unrelated working changes.

## Isolation and evidence

Checks execute through Bubblewrap with no network, separate user/PID/IPC/UTS namespaces, cleared environment, dropped capabilities, read-only system runtimes/certificates, disposable temporary/home directories, and only the snapshot writable. Source files, host home, Git metadata, and arbitrary host directories are not mounted. There is no unsandboxed fallback.

Each check has a 300-second default deadline and a 1 MiB aggregate stdout/stderr cap. Output overflow and timeout terminate the process group and Bubblewrap namespace, retain bounded diagnostics, and cannot establish a pass. The Linux exec wrapper applies per-process hard limits of 1 GiB address space, 64 MiB file size, 128 processes per real UID, 256 descriptors, and finite CPU time. These are per-process/UID limits, not aggregate host protection.

For aggregate limits on macOS or other non-Linux hosts, build `Dockerfile` and use `scripts/container.py`. Its defaults enforce cgroup memory at 2 GiB with no swap, 256 processes, and two CPUs. The container runs nonroot with no added capabilities, no network, a read-only root/runner/source, and bounded temporary storage. Nested rootless Bubblewrap requires explicit `seccomp=unconfined` and `systempaths=unconfined` Docker exceptions on the tested host. These remove Docker's default syscall and masked-proc protections. Bubblewrap and cgroups remain enforced; this configuration is not a uniform hostile-code security guarantee. Unsupported namespace setup fails visibly.

Every attempt has stdout/stderr captures with SHA-256 and byte count. Verification rejects missing metadata, changed artifacts, symlink aliases, inconsistent references, and unsandboxed pass attempts. Finding sources must name recorded checks and reference captures from that same check. The [finding schema](../templates/findings.schema.json) requires impact, confidence, action, and counterargument; legacy input cannot fabricate them. Contextual findings from inspection belong in the agent report unless represented by captured checks.

Serialized attempts require an explicit boolean `sandboxed`. Programmatic omission defaults to false and cannot support a pass. The flag records the runner's claim; hashes and flags do not authenticate who produced the evidence.

## Tool signals and history

SARIF is an interchange format for tool signals, not a replacement for contextual findings. Import a verified check capture, rank review attention, and export SARIF:

```bash
python3 scripts/run.py import-sarif --manifest manifest.json --check scanner --output signals.json
python3 scripts/run.py rank-hotspots --input signals.json --repo /absolute/repo --lookback-days 90 --revision HEAD --output ranked.json
python3 scripts/run.py export-sarif --signals ranked.json --output results.sarif
```

Use `--attempt` and `--stream` to select a capture. `--sarif file.sarif --repo /absolute/repo` imports an external file without pretending it was captured by the runner. Locations must resolve within the repository; invalid essential fields and escaping URIs are errors. Tool messages, rules, and levels remain signals. The agent must supply the repository-specific impact, confidence, counterargument, and proposed action before promoting one to a contextual finding.

Verified sandboxed captures may report absolute `/workspace/` file URIs or URI bases. Import translates that known mount root to repository-relative paths before containment checks. Unsandboxed captures and external-file imports receive no such allowance.

History ranking counts commits touching a location during an explicit lookback ending at the selected revision. It uses unsimplified path history so merged-and-reverted branch changes remain counted. It changes review order, not tool severity or defect status. Rename following is not included; shallow or unavailable history remains an explicit limitation. For GitHub uploads, avoid multiple runs sharing the same tool and category. Different tools/categories are supported; this is not a ban on all multi-run SARIF.

Diagnosis can export one recorded tool directly:

```bash
python3 scripts/run.py diagnose --spec run.json --sarif-check scanner --sarif-tool ToolName
```

The selected check's stdout must contain valid SARIF. The container launcher accepts the same paired flags. The manual [SARIF workflow](../.github/workflows/sarif-interchange.yml) either runs a committed diagnosis spec under the bounded container or normalizes a committed capture. It runs only from the default branch. Normalization has read-only repository permissions; a separate optional upload job holds `security-events: write`. Absolute check working directories are remapped with the snapshot root. Normalization disables bytecode writes before importing runner modules.

## Optional oracle sensitivity

```bash
python3 scripts/run.py mutation-audit --spec mutants.json --output sensitivity.json
```

Use a bounded write specification with one supplied mutation per step. Each step is evaluated independently against the same clean baseline in its own snapshot, not chained after the preceding mutant. Preimage hashes therefore refer to that baseline. Restrict mutations to the task's affected production paths and useful changed logic. The runner does not generate arbitrary mutants or weaken verification inputs.

The audit reports `detected`, `survived`, or `inconclusive` with manifests and captures. Stable check failures support detection. Timeouts, recognized resource diagnostics, signal-style exits, unavailable checks, rejected edits, and failing baselines are inconclusive. Signal-style exits are conservative because the runner cannot distinguish a resource kill from a functional crash. Opaque tool failures do not prove assertion coverage. Review survivors for weak assertions or semantic equivalence; do not enforce an arbitrary score or claim that every survivor is a defect. There is no autonomous repair loop.

## Unsigned provenance

Run CLI results include `provenance.json`, an unsigned in-toto Statement v1 using the SLSA provenance v1 predicate. Subjects hash the actual manifest and exported patch when present. Parameters, source revision, recorded attempts, and phase artifact identities describe the execution. The existing manifest remains authoritative for local gate validation. The statement has no signature, supplies no independent proof of isolation, and claims no SLSA security level.

## Linux container use

```bash
docker build -t anti-slop-runtime:local .
python3 scripts/container.py run --spec run.json --snapshot /tmp/task-snapshots --evidence /tmp/task-evidence
python3 scripts/container.py test
python3 scripts/container.py exec --evidence /tmp/e2e-evidence -- /usr/bin/python3 e2e.py --output /evidence/run
```

`--snapshot` names an empty dedicated parent; the runner creates its `workspace/` child. Source and runner mounts are read-only. Container specs rewrite source/snapshot paths and absolute check working directories. Result paths are container paths under `/evidence`; their host files are under the selected evidence directory. `exec --evidence` retains evaluation outputs after the container exits. Other explicit `exec` commands use disposable temporary storage. No command applies an exported patch to the source.

New output directories are private to the selected container identity. A host-root launcher selects UID/GID 65534, provisions only newly created mount roots for that identity, and trusts only the explicit `/source` Git repository. Existing directories and parents keep their ownership and permissions; inaccessible existing outputs are rejected before launch. Mapped specs are exclusive private files.


## Verification

From `scripts/`:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q run.py anti_slop_core tests
python3 run.py --help
```

The suite includes deterministic fixture tests and actual CLI/Bubblewrap tests. Real isolation tests capability-probe and explicitly skip when the host cannot start Bubblewrap; skips are not sandbox verification. See [acceptance results](../research/acceptance-results.md), [pilot](../research/pilot-results.md), and [skill evaluation](../research/skill-evaluation.md) for recorded evidence and limits. Keep implementation standard-library-only and preserve source research.
